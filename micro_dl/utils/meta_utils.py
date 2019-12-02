import os
import pandas as pd
import micro_dl.utils.aux_utils as aux_utils
import micro_dl.utils.mp_utils as mp_utils
import itertools

def frames_meta_generator(
        input_dir,
        order='cztp',
        name_parser='parse_sms_name',
        ):
    """
    Generate metadata from file names for preprocessing.
    Will write found data in frames_metadata.csv in input directory.
    Assumed default file naming convention is:
    dir_name
    |
    |- im_c***_z***_t***_p***.png
    |- im_c***_z***_t***_p***.png

    c is channel
    z is slice in stack (z)
    t is time
    p is position (FOV)

    Other naming convention is:
    img_channelname_t***_p***_z***.tif for parse_sms_name

    :param list args:    parsed args containing
        str input_dir:   path to input directory containing images
        str name_parser: Function in aux_utils for parsing indices from file name
    """
    parse_func = aux_utils.import_object('utils.aux_utils', name_parser, 'function')
    im_names = aux_utils.get_sorted_names(input_dir)
    frames_meta = aux_utils.make_dataframe(nbr_rows=len(im_names))
    channel_names = []
    # Fill dataframe with rows from image names
    for i in range(len(im_names)):
        kwargs = {"im_name": im_names[i]}
        if name_parser == 'parse_idx_from_name':
            kwargs["order"] = order
        elif name_parser == 'parse_sms_name':
            kwargs["channel_names"] = channel_names
        meta_row = parse_func(**kwargs)
        meta_row['dir_name'] = input_dir
        frames_meta.loc[i] = meta_row
    # Write metadata
    frames_meta_filename = os.path.join(input_dir, 'frames_meta.csv')
    frames_meta.to_csv(frames_meta_filename, sep=",")
    return frames_meta

def ints_meta_generator(
        input_dir,
        order='cztp',
        name_parser='parse_sms_name',
        num_workers=4
        ):
    """
    Generate metadata from file names for preprocessing.
    Will write found data in frames_metadata.csv in input directory.
    Assumed default file naming convention is:
    dir_name
    |
    |- im_c***_z***_t***_p***.png
    |- im_c***_z***_t***_p***.png

    c is channel
    z is slice in stack (z)
    t is time
    p is position (FOV)

    Other naming convention is:
    img_channelname_t***_p***_z***.tif for parse_sms_name

    :param list args:    parsed args containing
        str input_dir:   path to input directory containing images
        str name_parser: Function in aux_utils for parsing indices from file name
    """
    parse_func = aux_utils.import_object('utils.aux_utils', name_parser, 'function')
    im_names = aux_utils.get_sorted_names(input_dir)
    channel_names = []
    mp_fn_args = []
    mp_block_args = []
    block_size = 256
    # Fill dataframe with rows from image names
    for i in range(len(im_names)):
        kwargs = {"im_name": im_names[i]}
        if name_parser == 'parse_idx_from_name':
            kwargs["order"] = order
        elif name_parser == 'parse_sms_name':
            kwargs["channel_names"] = channel_names
        meta_row = parse_func(**kwargs)
        meta_row['dir_name'] = input_dir
        im_path = os.path.join(input_dir, im_names[i])
        mp_fn_args.append(im_path)
        mp_block_args.append((im_path, block_size, meta_row))

    im_ints_list = mp_utils.mp_sample_im_pixels(mp_block_args, num_workers)
    im_ints_list = list(itertools.chain.from_iterable(im_ints_list))
    ints_meta = pd.DataFrame.from_dict(im_ints_list)

    ints_meta_filename = os.path.join(input_dir, 'ints_meta.csv')
    ints_meta.to_csv(ints_meta_filename, sep=",")
    return ints_meta

def compute_zscore_params(frames_meta,
                          ints_meta,
                          input_dir,
                          normalize_im,
                          min_fraction=0):
    """Get zscore mean and standard deviation

    :param int time_idx: Time index
    :param int channel_idx: Channel index
    :param int slice_idx: Slice (z) index
    :param int pos_idx: Position (FOV) index
    :param int slice_ids: Index of which focal plane acquisition to
         use (for 2D).
    :param str mask_dir: Directory containing masks
    :param None or str normalize_im: normalization scheme for input images
    :param dataframe frames_meta: metadata contains mean and std info of each z-slice
    :return float zscore_mean: mean for z-scoring the image
    :return float zscore_std: std for z-scoring the image
    """

    assert normalize_im in [None, 'slice', 'volume', 'dataset'], \
        'normalize_im must be None or "slice" or "volume" or "dataset"'

    if normalize_im is None:
        # No normalization
        frames_meta['zscore_median'] = 0
        frames_meta['zscore_median'] = 1
        return frames_meta

    elif normalize_im == 'dataset':
        agg_cols = ['time_idx', 'channel_idx', 'dir_name']
    elif normalize_im == 'volume':
        agg_cols = ['time_idx', 'channel_idx', 'dir_name', 'pos_idx']
    else:
        agg_cols = ['time_idx', 'channel_idx', 'dir_name', 'pos_idx', 'slice_idx']
    # median and inter-quartile range are more robust than mean and std
    ints_meta = ints_meta[ints_meta['fg_frac'] >= min_fraction]
    ints_agg_median = \
        ints_meta[agg_cols + ['intensity']].groupby(agg_cols).median()
    ints_agg_hq = \
        ints_meta[agg_cols + ['intensity']].groupby(agg_cols).quantile(0.75)
    ints_agg_lq = \
        ints_meta[agg_cols + ['intensity']].groupby(agg_cols).quantile(0.25)
    ints_agg = ints_agg_median
    ints_agg.columns = ['zscore_median']
    ints_agg['zscore_iqr'] = ints_agg_hq['intensity'] - ints_agg_lq['intensity']
    ints_agg.reset_index(inplace=True)
    cols_to_merge = \
        frames_meta.columns[[
            col not in ['zscore_median', 'zscore_iqr']
            for col in frames_meta.columns]]
    frames_meta = \
        pd.merge(frames_meta[cols_to_merge], ints_agg, how='left', on=agg_cols)
    frames_meta_filename = os.path.join(input_dir, 'frames_meta.csv')
    frames_meta.to_csv(frames_meta_filename, sep=",")

    return frames_meta



