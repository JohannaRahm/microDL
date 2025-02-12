import copy
import numpy as np
import os
import pandas as pd

import micro_dl.utils.aux_utils as aux_utils
from micro_dl.preprocessing.tile_uniform_images import ImageTilerUniform
from micro_dl.utils.mp_utils import mp_tile_save, mp_crop_save


class ImageTilerNonUniform(ImageTilerUniform):
    """Tiles all images images in a dataset"""

    def __init__(self,
                 input_dir,
                 output_dir,
                 tile_size=[256, 256],
                 step_size=[64, 64],
                 depths=1,
                 time_ids=-1,
                 channel_ids=-1,
                 normalize_channels=-1,
                 slice_ids=-1,
                 pos_ids=-1,
                 hist_clip_limits=None,
                 flat_field_dir=None,
                 image_format='zyx',
                 num_workers=4,
                 int2str_len=3,
                 tile_3d=False,
                 tiles_exist=False):
        """Init

        Assuming same structure across channels and same number of samples
        across channels. The dataset could have varying number of time points
        and / or varying number of slices / size for each sample / position
        Please ref to init of ImageTilerUniform.
        """

        super().__init__(input_dir=input_dir,
                         output_dir=output_dir,
                         tile_size=tile_size,
                         step_size=step_size,
                         depths=depths,
                         time_ids=time_ids,
                         channel_ids=channel_ids,
                         normalize_channels=normalize_channels,
                         slice_ids=slice_ids,
                         pos_ids=pos_ids,
                         hist_clip_limits=hist_clip_limits,
                         flat_field_dir=flat_field_dir,
                         image_format=image_format,
                         num_workers=num_workers,
                         int2str_len=int2str_len,
                         tile_3d=tile_3d,
                         tiles_exist=tiles_exist)
        # Get metadata indices
        metadata_ids, nested_id_dict = aux_utils.validate_metadata_indices(
            frames_metadata=self.frames_metadata,
            time_ids=time_ids,
            channel_ids=channel_ids,
            slice_ids=slice_ids,
            pos_ids=pos_ids,
            uniform_structure=False
        )
        self.nested_id_dict = nested_id_dict
        # self.tile_dir is already created in super(). Check if frames_meta
        # exists in self.tile_dir
        meta_path = os.path.join(self.tile_dir, 'frames_meta.csv')
        assert not os.path.exists(meta_path), 'Tile dir exists. ' \
                                              'cannot add to existing dir'

    def tile_first_channel(self,
                           channel0_ids,
                           channel0_depth,
                           cur_mask_dir=None,
                           is_mask=False):
        """Tile first channel or mask and use the tile indices for the rest

        Tiles and saves the tiles, meta_df for each image in
        self.tile_dir/meta_dir. The list of meta_df for all images gets saved
        as frames_meta.csv

        :param dict channel0_ids: [tp_idx][ch_idx][ch_dict] for first channel
         or mask channel
        :param int channel0_depth: image depth for first channel or mask
        :param str cur_mask_dir: mask dir if tiling mask channel else none
        :param bool is_mask: Is mask channel
        :return pd.DataFrame ch0_meta_df: pd.Dataframe with ids, row_start
         and col_start
        """

        fn_args = []
        for tp_idx, tp_dict in channel0_ids.items():
            for ch_idx, ch_dict in tp_dict.items():
                if is_mask:
                    normalize_im = False
                else:
                    normalize_im = self.normalize_channels[ch_idx]
                for pos_idx, sl_idx_list in ch_dict.items():
                    cur_sl_idx_list = aux_utils.adjust_slice_margins(
                        sl_idx_list, channel0_depth
                    )
                    for sl_idx in cur_sl_idx_list:
                        cur_args = super().get_crop_tile_args(
                            channel_idx=ch_idx,
                            time_idx=tp_idx,
                            slice_idx=sl_idx,
                            pos_idx=pos_idx,
                            task_type='tile',
                            mask_dir=cur_mask_dir,
                        )
                        fn_args.append(cur_args)

        # tile_image uses min_fraction assuming input_image is a bool
        ch0_meta_df_list = mp_tile_save(fn_args, workers=self.num_workers)

        ch0_meta_df = pd.concat(ch0_meta_df_list, ignore_index=True)
        # Finally, save all the metadata
        ch0_meta_df = ch0_meta_df.sort_values(by=['file_name'])
        ch0_meta_df.to_csv(os.path.join(self.tile_dir, 'frames_meta.csv'),
                           sep=",")
        return ch0_meta_df

    def tile_remaining_channels(self,
                                nested_id_dict,
                                tiled_ch_id,
                                cur_meta_df):
        """Tile remaining channels using tile indices of 1st channel / mask

        :param dict nested_id_dict: nested dict with time, channel, pos and
         slice indices
        :param int tiled_ch_id: self.channel_ids[0] or mask_channel
        :param pd.DataFrame cur_meta_df: DF with meta for the already tiled
         channel
        """

        fn_args = []
        for tp_idx, tp_dict in nested_id_dict.items():
            for ch_idx, ch_dict in tp_dict.items():
                for pos_idx, sl_idx_list in ch_dict.items():
                    cur_sl_idx_list = aux_utils.adjust_slice_margins(
                        sl_idx_list, self.channel_depth[ch_idx]
                    )
                    for sl_idx in cur_sl_idx_list:
                        cur_tile_indices = super()._get_tile_indices(
                            tiled_meta=cur_meta_df,
                            time_idx=tp_idx,
                            channel_idx=tiled_ch_id,
                            pos_idx=pos_idx,
                            slice_idx=sl_idx
                        )
                        # Find channel index position in channel_ids list
                        list_idx = self.channel_ids.index(ch_idx)
                        if np.any(cur_tile_indices):
                            cur_args = super().get_crop_tile_args(
                                ch_idx,
                                tp_idx,
                                sl_idx,
                                pos_idx,
                                task_type='crop',
                                tile_indices=cur_tile_indices,
                            )
                            fn_args.append(cur_args)

        tiled_meta_df_list = mp_crop_save(
            fn_args,
            workers=self.num_workers,
        )
        tiled_metadata = pd.concat(tiled_meta_df_list, ignore_index=True)
        tiled_metadata = pd.concat(
            [cur_meta_df.reset_index(drop=True),
             tiled_metadata.reset_index(drop=True)],
            axis=0,
            ignore_index=True,
        )
        # Finally, save all the metadata
        tiled_metadata = tiled_metadata.sort_values(by=['file_name'])
        tiled_metadata.to_csv(
            os.path.join(self.tile_dir, "frames_meta.csv"),
            sep=",",
        )

    def tile_stack(self):
        """Tiles images in the specified channels.

        Assuming mask channel is not included in frames_meta in self.input_dir.
        Else this will cause an error as the filename = self.input_dir +
        file_name from frames_meta.csv. Masks are generally stored in a
        different folder.

        Saves a csv with columns
        ['time_idx', 'channel_idx', 'pos_idx','slice_idx', 'file_name']
        for all the tiles
        """

        ch_to_tile = self.channel_ids[0]
        ch_depth = self.channel_depth[ch_to_tile]

        # create a copy of nested_id_dict to remove the entries of the first
        # channel
        nested_id_dict_copy = copy.deepcopy(self.nested_id_dict)

        ch0_ids = {}
        for tp_idx, tp_dict in self.nested_id_dict.items():
            for ch_idx, ch_dict in tp_dict.items():
                if ch_idx == ch_to_tile:
                    ch0_dict = {ch_idx: ch_dict}
                    del nested_id_dict_copy[tp_idx][ch_idx]
            ch0_ids[tp_idx] = ch0_dict

        # tile first channel and use the tile indices to tile the rest
        meta_df = self.tile_first_channel(channel0_ids=ch0_ids,
                                          channel0_depth=ch_depth)
        # remove channel 0 from self.channel_ids
        _ = self.channel_ids.pop(0)
        if self.channel_ids:
            self.tile_remaining_channels(nested_id_dict=nested_id_dict_copy,
                                         tiled_ch_id=ch_to_tile,
                                         cur_meta_df=meta_df)

    def tile_mask_stack(self,
                        mask_dir,
                        mask_channel,
                        mask_depth=1):
        """
        Tiles images in the specified channels assuming there are masks
        already created in mask_dir. Only tiles above a certain fraction
        of foreground in mask tile will be saved and added to metadata.


        Saves a csv with columns ['time_idx', 'channel_idx', 'pos_idx',
        'slice_idx', 'file_name'] for all the tiles

        :param str mask_dir: Directory containing masks
        :param int mask_channel: Channel number assigned to mask
        :param int mask_depth: Depth for mask channel
        """

        # mask depth has to match input or output channel depth
        assert mask_depth <= max(self.channel_depth.values())
        self.mask_depth = mask_depth

        # Mask meta is stored in mask dir. If channel_ids= -1,frames_meta will
        # not contain any rows for mask channel. Assuming structure is same
        # across channels. Get time, pos and slice indices for mask channel

        mask_meta_df = aux_utils.read_meta(mask_dir)
        _, mask_nested_id_dict = aux_utils.validate_metadata_indices(
            frames_metadata=mask_meta_df,
            time_ids=self.time_ids,
            channel_ids=mask_channel,
            slice_ids=self.slice_ids,
            pos_ids=self.pos_ids,
            uniform_structure=False
        )

        # get t, z, p indices for mask_channel
        mask_ch_ids = {}
        for tp_idx, tp_dict in mask_nested_id_dict.items():
            for ch_idx, ch_dict in tp_dict.items():
                if ch_idx == mask_channel:
                    ch0_dict = {mask_channel: ch_dict}
                    mask_ch_ids[tp_idx] = ch0_dict

        # tile mask channel and use the tile indices to tile the rest
        meta_df = self.tile_first_channel(
            channel0_ids=mask_ch_ids,
            channel0_depth=mask_depth,
            cur_mask_dir=mask_dir,
            is_mask=True,
        )
        # tile the rest
        self.tile_remaining_channels(
            nested_id_dict=self.nested_id_dict,
            tiled_ch_id=mask_channel,
            cur_meta_df=meta_df,
        )
