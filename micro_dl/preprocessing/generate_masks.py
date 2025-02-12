"""Generate masks from sum of flurophore channels"""
import os
import pandas as pd

import micro_dl.utils.aux_utils as aux_utils
from micro_dl.utils.mp_utils import mp_create_save_mask
from skimage.filters import threshold_otsu


class MaskProcessor:
    """Generate masks from channels"""

    def __init__(self,
                 input_dir,
                 output_dir,
                 channel_ids,
                 flat_field_dir=None,
                 time_ids=-1,
                 slice_ids=-1,
                 pos_ids=-1,
                 int2str_len=3,
                 uniform_struct=True,
                 num_workers=4,
                 mask_type='otsu',
                 mask_channel=None,
                 mask_ext='.npy',
                 ):
        """
        :param str input_dir: Directory with image frames
        :param str output_dir: Base output directory
        :param list[int] channel_ids: Channel indices to be masked (typically
            just one)
        :param str flat_field_dir: Directory with flatfield images if
            flatfield correction is applied
        :param int/list channel_ids: generate mask from the sum of these
            (flurophore) channel indices
        :param list/int time_ids: timepoints to consider
        :param int slice_ids: Index of which focal plane (z)
            acquisition to use (default -1 includes all slices)
        :param int pos_ids: Position (FOV) indices to use
        :param int int2str_len: Length of str when converting ints
        :param bool uniform_struct: bool indicator for same structure across
            pos and time points
        :param int num_workers: number of workers for multiprocessing
        :param str mask_type: method to use for generating mask. Needed for
            mapping to the masking function
        :param int mask_channel: channel number assigned to to be generated masks.
            If resizing images on a subset of channels, frames_meta is from resize
            dir, which could lead to wrong mask channel being assigned.
        :param str mask_ext: '.npy' or 'png'. Save the mask as uint8 PNG or
            NPY files
        :param bool normalize_im: indicator to normalize image based on z-score or not
        """

        self.input_dir = input_dir
        self.output_dir = output_dir
        self.flat_field_dir = flat_field_dir
        self.num_workers = num_workers

        self.frames_metadata = aux_utils.read_meta(self.input_dir)
        if 'dir_name' not in self.frames_metadata.keys():
            self.frames_metadata['dir_name'] = self.input_dir
        # Create a unique mask channel number so masks can be treated
        # as a new channel
        if mask_channel is None:
            self.mask_channel = int(
                self.frames_metadata['channel_idx'].max() + 1
            )
        else:
            self.mask_channel = int(mask_channel)

        metadata_ids, nested_id_dict = aux_utils.validate_metadata_indices(
            frames_metadata=self.frames_metadata,
            time_ids=time_ids,
            channel_ids=channel_ids,
            slice_ids=slice_ids,
            pos_ids=pos_ids,
            uniform_structure=uniform_struct,
        )
        self.frames_meta_sub = aux_utils.get_sub_meta(
            frames_metadata=self.frames_metadata,
            time_ids=metadata_ids['time_ids'],
            channel_ids=metadata_ids['channel_ids'],
            slice_ids=metadata_ids['slice_ids'],
            pos_ids=metadata_ids['pos_ids'])
        self.channel_ids = metadata_ids['channel_ids']
        output_channels = '-'.join(map(str, self.channel_ids))
        if mask_type is 'borders_weight_loss_map':
            output_channels = str(mask_channel)
        # Create mask_dir as a subdirectory of output_dir
        self.mask_dir = os.path.join(
            self.output_dir,
            'mask_channels_' + output_channels,
        )
        os.makedirs(self.mask_dir, exist_ok=True)

        self.int2str_len = int2str_len
        self.uniform_struct = uniform_struct
        self.nested_id_dict = nested_id_dict

        assert mask_type in ['otsu', 'unimodal', 'dataset otsu', 'borders_weight_loss_map'], \
            "Masking method invalid, 'otsu', 'unimodal', 'dataset otsu', 'borders_weight_loss_map'\
             are currently supported"
        self.mask_type = mask_type
        self.ints_metadata = None
        self.channel_thr_df = None
        if mask_type == 'dataset otsu':
            self.ints_metadata = aux_utils.read_meta(self.input_dir, 'intensity_meta.csv')
            self.channel_thr_df = self.get_channel_thr_df()
        # for channel_idx in channel_ids:
        #     row_idxs = self.ints_metadata['channel_idx'] == channel_idx
        #     pix_ints = self.ints_metadata.loc[row_idxs, 'intensity'].values
        #     self.channel_thr = threshold_otsu(pix_ints, nbins=32)
        #     # self.channel_thr = get_unimodal_threshold(pix_ints)
        #     self.channel_thr_df.append(0.3 * self.channel_thr)
        #     # self.channel_thr_df.append(1 * self.channel_thr)
        self.mask_ext = mask_ext

    def get_channel_thr_df(self):
        ints_meta_sub = self.ints_metadata.loc[
            self.ints_metadata['channel_idx'].isin(self.channel_ids),
            ['dir_name', 'channel_idx', 'intensity']
        ]
        # channel_thr_df = ints_meta_sub.groupby(['dir_name', 'channel_idx']).agg(get_unimodal_threshold).reset_index()
        channel_thr_df = ints_meta_sub.groupby(['dir_name', 'channel_idx']).agg(threshold_otsu).reset_index()
        channel_thr_df['intensity'] = channel_thr_df['intensity']
        return channel_thr_df

    def get_mask_dir(self):
        """
        Return mask directory
        :return str mask_dir: Directory where masks are stored
        """
        return self.mask_dir

    def get_mask_channel(self):
        """
        Return mask channel
        :return int mask_channel: Assigned channel number for mask
        """
        return self.mask_channel

    def _get_args_read_image(self,
                             time_idx,
                             channel_ids,
                             slice_idx,
                             pos_idx,
                             correct_flat_field):
        """
        Read image from t, c, p and s indices. All indices are singular
        except channel which can be a list

        :param int time_idx: Current time point to use for generating mask
        :param list channel_ids: channel ids to use for generating mask
        :param int slice_idx: Slice index
        :param int pos_idx: Position index
        :param bool correct_flat_field: bool indicator to correct for flat
            field
        :return np.array im: image corresponding to the given channel indices
            and flatfield corrected
        """

        input_fnames = []
        for channel_idx in channel_ids:
            frame_idx = aux_utils.get_meta_idx(self.frames_metadata,
                                               time_idx,
                                               channel_idx,
                                               slice_idx,
                                               pos_idx)
            file_path = os.path.join(
                self.input_dir,
                self.frames_metadata.loc[frame_idx, 'file_name'],
            )
            input_fnames.append(file_path)

        flat_field_fname = None
        if correct_flat_field:
            if isinstance(channel_idx, (int, float)):
                flat_field_fname = os.path.join(
                    self.flat_field_dir,
                    'flat-field_channel-{}.npy'.format(channel_idx)
                )
            elif isinstance(channel_idx, (tuple, list)):
                flat_field_fname = []
                for ch_idx in channel_idx:
                    flat_field_fname.append(os.path.join(
                        self.flat_field_dir,
                        'flat-field_channel-{}.npy'.format(ch_idx)
                    ))
        return tuple(input_fnames), flat_field_fname

    def generate_masks(self,
                       correct_flat_field=False,
                       str_elem_radius=5):
        """
        Generate masks from flat-field corrected flurophore images.
        The sum of flurophore channels is thresholded to generate a foreground
        mask.

        :param bool correct_flat_field: bool indicator to correct for flat
         field or not
        :param int str_elem_radius: Radius of structuring element for
         morphological operations
        """

        # Loop through all the indices and create masks
        fn_args = []
        id_df = self.frames_meta_sub[
            ['dir_name', 'time_idx', 'pos_idx', 'slice_idx']
        ].drop_duplicates()
        channel_thrs = None
        if self.uniform_struct:
            for id_row in id_df.to_numpy():
                dir_name, time_idx, pos_idx, slice_idx = id_row
                input_fnames, ff_fname = self._get_args_read_image(
                    time_idx=time_idx,
                    channel_ids=self.channel_ids,
                    slice_idx=slice_idx,
                    pos_idx=pos_idx,
                    correct_flat_field=correct_flat_field,
                )
                if self.mask_type == 'dataset otsu':
                    channel_thrs = self.channel_thr_df.loc[
                        self.channel_thr_df['dir_name'] == dir_name, 'intensity'].to_numpy()
                cur_args = (input_fnames,
                            ff_fname,
                            str_elem_radius,
                            self.mask_dir,
                            self.mask_channel,
                            time_idx,
                            pos_idx,
                            slice_idx,
                            self.int2str_len,
                            self.mask_type,
                            self.mask_ext,
                            channel_thrs)
                fn_args.append(cur_args)
        else:
            for tp_idx, tp_dict in self.nested_id_dict.items():
                mask_channel_dict = tp_dict[self.channel_ids[0]]
                for pos_idx, sl_idx_list in mask_channel_dict.items():
                    for sl_idx in sl_idx_list:
                        input_fnames, ff_fname = self._get_args_read_image(
                            time_idx=tp_idx,
                            channel_ids=self.channel_ids,
                            slice_idx=sl_idx,
                            pos_idx=pos_idx,
                            correct_flat_field=correct_flat_field,
                        )
                        cur_args = (input_fnames,
                                    ff_fname,
                                    str_elem_radius,
                                    self.mask_dir,
                                    self.mask_channel,
                                    tp_idx,
                                    pos_idx,
                                    sl_idx,
                                    self.int2str_len,
                                    self.mask_type,
                                    self.mask_ext)
                        fn_args.append(cur_args)

        mask_meta_list = mp_create_save_mask(fn_args, self.num_workers)
        mask_meta_df = pd.DataFrame.from_dict(mask_meta_list)
        mask_meta_df = mask_meta_df.sort_values(by=['file_name'])
        mask_meta_df.to_csv(
            os.path.join(self.mask_dir, 'frames_meta.csv'),
            sep=',')
        # update fg_frac field in image frame_meta.csv
        cols_to_merge = self.frames_metadata.columns[self.frames_metadata.columns != 'fg_frac']
        self.frames_metadata = \
            pd.merge(self.frames_metadata[cols_to_merge],
                     mask_meta_df[['pos_idx', 'time_idx', 'slice_idx', 'fg_frac']],
                     how='left', on=['pos_idx', 'time_idx', 'slice_idx'])
        self.frames_metadata.to_csv(os.path.join(self.input_dir, 'frames_meta.csv'),
                                    sep=',')
