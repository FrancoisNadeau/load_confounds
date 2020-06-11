"""
Load confounds generated by fMRIprep.

Authors: Hanad Sharmarke, Dr. Pierre Bellec, Francois Paugam 
"""
import itertools
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import warnings

# Global variables listing the admissible types of noise components
all_confounds = ["motion", "high_pass", "wm_csf", "global", "compcor"]


def _add_suffix(params, model):
    """
    Add suffixes to a list of parameters.
    Suffixes includes derivatives, power2 and full
    """
    params_full = params.copy()
    for par in params:
        if (model == "derivatives") or (model == "full"):
            params_full.append(f"{par}_derivative1")
        if (model == "power2") or (model == "full"):
            params_full.append(f"{par}_power2")
        if model == "full":
            params_full.append(f"{par}_derivative1_power2")
    return params_full


def _check_params(confounds_raw, params):
    """Check that specified parameters can be found in the confounds."""
    for par in params:
        if not par in confounds_raw.columns:
            raise ValueError(
                f"The parameter {par} cannot be found in the available confounds. You may want to use a different denoising strategy'"
            )

    return None


def _find_confounds(confounds_raw, keywords):
    """Find confounds that contain certain keywords."""
    list_confounds = []
    for key in keywords:
        key_found = False
        for col in confounds_raw.columns:
            if key in col:
                list_confounds.append(col)
                key_found = True
        if not key_found:
            raise ValueError(f"could not find any confound with the key {key}")
    return list_confounds


def _load_global(confounds_raw, global_signal):
    """Load the regressors derived from the global signal."""
    global_params = _add_suffix(["global_signal"], global_signal)
    _check_params(confounds_raw, global_params)
    return confounds_raw[global_params]


def _load_wm_csf(confounds_raw, wm_csf):
    """Load the regressors derived from the white matter and CSF masks."""
    wm_csf_params = _add_suffix(["csf", "white_matter"], wm_csf)
    _check_params(confounds_raw, wm_csf_params)
    return confounds_raw[wm_csf_params]


def _load_high_pass(confounds_raw):
    """Load the high pass filter regressors."""
    high_pass_params = _find_confounds(confounds_raw, ["cosine"])
    return confounds_raw[high_pass_params]


def _label_compcor(confounds_raw, compcor_suffix, n_compcor):
    """Builds list for the number of compcor components."""
    compcor_cols = []
    for nn in range(n_compcor + 1):
        nn_str = str(nn).zfill(2)
        compcor_col = compcor_suffix + "_comp_cor_" + nn_str
        if compcor_col not in confounds_raw.columns:
            warnings.warn(f"could not find any confound with the key {compcor_col}")
        else:
            compcor_cols.append(compcor_col)

    return compcor_cols


def _load_compcor(confounds_raw, compcor, n_compcor):
    """Load compcor regressors."""
    if compcor == "anat":
        compcor_cols = _label_compcor(confounds_raw, "a", n_compcor)

    if compcor == "temp":
        compcor_cols = _label_compcor(confounds_raw, "t", n_compcor)

    if compcor == "full":
        compcor_cols = _label_compcor(confounds_raw, "a", n_compcor)
        compcor_cols.extend(_label_compcor(confounds_raw, "t", n_compcor))

    compcor_cols.sort()
    _check_params(confounds_raw, compcor_cols)
    return confounds_raw[compcor_cols]


def _load_motion(confounds_raw, motion, n_motion):
    """Load the motion regressors."""
    motion_params = _add_suffix(
        ["trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z"], motion
    )
    _check_params(confounds_raw, motion_params)
    confounds_motion = confounds_raw[motion_params]

    # Optionally apply PCA reduction
    if n_motion > 0:
        confounds_motion = _pca_motion(confounds_motion, n_components=n_motion)

    return confounds_motion


def _pca_motion(confounds_motion, n_components):
    """Reduce the motion paramaters using PCA."""
    confounds_motion = confounds_motion.dropna()
    scaler = StandardScaler(with_mean=True, with_std=True)
    confounds_motion_std = scaler.fit_transform(confounds_motion)
    pca = PCA(n_components=n_components)
    motion_pca = pd.DataFrame(pca.fit_transform(confounds_motion_std))
    motion_pca.columns = ["motion_pca_" + str(col + 1) for col in motion_pca.columns]
    return motion_pca


def _sanitize_strategy(strategy):
    """Defines the supported denoising strategies."""
    if isinstance(strategy, list):
        for conf in strategy:
            if not conf in all_confounds:
                raise ValueError(f"{conf} is not a supported type of confounds.")
    else:
        raise ValueError("strategy needs to be a list of strings")
    return strategy


def _confounds2df(confounds_raw):
    """Load raw confounds as a pandas DataFrame."""
    if not isinstance(confounds_raw, pd.DataFrame):
        if "nii" in confounds_raw[-6:]:
            suffix = "_space-" + confounds_raw.split("space-")[1]
            confounds_raw = confounds_raw.replace(
                suffix, "_desc-confounds_regressors.tsv",
            )
        confounds_raw = pd.read_csv(confounds_raw, delimiter="\t", encoding="utf-8")
    return confounds_raw


def _sanitize_confounds(confounds_raw):
    """Make sure the inputs are in the correct format."""
    # we want to support loading a single set of confounds, instead of a list
    # so we hack it
    flag_single = isinstance(confounds_raw, str) or isinstance(
        confounds_raw, pd.DataFrame
    )
    if flag_single:
        confounds_raw = [confounds_raw]

    return confounds_raw, flag_single


class Confounds:
    """
    Confounds from fmriprep

    Parameters
    ----------
    strategy : list of strings
        The type of noise confounds to include.
        "motion" head motion estimates.
        "high_pass" discrete cosines covering low frequencies.
        "wm_csf" confounds derived from white matter and cerebrospinal fluid.
        "global" confounds derived from the global signal.

    motion : string, optional
        Type of confounds extracted from head motion estimates.
        "basic" translation/rotation (6 parameters)
        "power2" translation/rotation + quadratic terms (12 parameters)
        "derivatives" translation/rotation + derivatives (12 parameters)
        "full" translation/rotation + derivatives + quadratic terms + power2d derivatives (24 parameters)

    n_motion : float
        Number of pca components to keep from head motion estimates.
        If the parameters is strictly comprised between 0 and 1, a principal component
        analysis is applied to the motion parameters, and the number of extracted
        components is set to exceed `n_motion` percent of the parameters variance.
        If the n_components = 0, then no PCA is performed.

    wm_csf : string, optional
        Type of confounds extracted from masks of white matter and cerebrospinal fluids.
        "basic" the averages in each mask (2 parameters)
        "power2" averages and quadratic terms (4 parameters)
        "derivatives" averages and derivatives (4 parameters)
        "full" averages + derivatives + quadratic terms + power2d derivatives (8 parameters)

    global_signal : string, optional
        Type of confounds extracted from the global signal.
        "basic" just the global signal (1 parameter)
        "power2" global signal and quadratic term (2 parameters)
        "derivatives" global signal and derivative (2 parameters)
        "full" global signal + derivatives + quadratic terms + power2d derivatives (4 parameters)

    compcor : string,optional
        Type of confounds extracted from a component based noise correction method
        "anat" noise components calculated using anatomical compcor
        "temp" noise components calculated using temporal compcor
        "full" noise components calculated using both temporal and anatomical

    n_compcor : int, optional
        The number of noise components to be extracted.

    Attributes
    ----------
    `confounds_` : pandas DataFrame
        The confounds loaded using the specified model

    Notes
    -----
    The predefined strategies implemented in this class are from
    adapted from (Ciric et al. 2017). Band-pass filter is replaced
    by high-pass filter, as high frequencies have been shown to carry
    meaningful signal for connectivity analysis.

    References
    ----------
    Ciric et al., 2017 "Benchmarking of participant-level confound regression
    strategies for the control of motion artifact in studies of functional
    connectivity" Neuroimage 154: 174-87
    https://doi.org/10.1016/j.neuroimage.2017.03.020
    """

    def __init__(
        self,
        strategy=["motion", "high_pass", "wm_csf"],
        motion="full",
        n_motion=0,
        wm_csf="basic",
        global_signal="basic",
        compcor="anat",
        n_compcor=6,
    ):
        self.strategy = _sanitize_strategy(strategy)
        self.motion = motion
        self.n_motion = n_motion
        self.wm_csf = wm_csf
        self.global_signal = global_signal
        self.compcor = compcor
        self.n_compcor = n_compcor

    def load(self, confounds_raw):
        """
        Load fMRIprep confounds

        Parameters
        ----------
        confounds_raw : Pandas Dataframe or path to tsv file(s), optionally as a list.
            Raw confounds from fmriprep

        Returns
        -------
        confounds :  pandas DataFrame or list of pandas DataFrame
            A reduced version of fMRIprep confounds based on selected strategy and flags.
        """
        confounds_raw, flag_single = _sanitize_confounds(confounds_raw)
        confounds_out = []
        for file in confounds_raw:
            confounds_out.append(self._load_single(file))

        # If a single input was provided,
        # send back a single output instead of a list
        if flag_single:
            confounds_out = confounds_out[0]

        self.confounds_ = confounds_out
        return confounds_out

    def _load_single(self, confounds_raw):
        """Load a single confounds file from fmriprep."""
        # Convert tsv file to pandas dataframe
        confounds_raw = _confounds2df(confounds_raw)

        confounds = pd.DataFrame()

        if "motion" in self.strategy:
            confounds_motion = _load_motion(confounds_raw, self.motion, self.n_motion)
            confounds = pd.concat([confounds, confounds_motion], axis=1)

        if "high_pass" in self.strategy:
            confounds_high_pass = _load_high_pass(confounds_raw)
            confounds = pd.concat([confounds, confounds_high_pass], axis=1)

        if "wm_csf" in self.strategy:
            confounds_wm_csf = _load_wm_csf(confounds_raw, self.wm_csf)
            confounds = pd.concat([confounds, confounds_wm_csf], axis=1)

        if "global" in self.strategy:
            confounds_global_signal = _load_global(confounds_raw, self.global_signal)
            confounds = pd.concat([confounds, confounds_global_signal], axis=1)

        if "compcor" in self.strategy:
            confounds_compcor = _load_compcor(
                confounds_raw, self.compcor, self.n_compcor
            )
            confounds = pd.concat([confounds, confounds_compcor], axis=1)

        return confounds


class P2(Confounds):
    """
    Load confounds using the 2P strategy from Ciric et al. 2017.
    Mean white matter and CSF signals, with high-pass filter.

    Parameters
    ----------
    confounds_raw : Pandas Dataframe or path to tsv file(s), optionally as a list.
        Raw confounds from fmriprep

    Returns
    -------
    conf :  a Confounds object
        conf.confounds_ is a reduced version of fMRIprep confounds.

    """

    def __init__(self):
        self.strategy = ["high_pass", "wm_csf"]
        self.wm_csf = "basic"


class P6(Confounds):
    """
    Load confounds using the 6P strategy from Ciric et al. 2017.
    Basic motion parameters with high pass filter.

    Parameters
    ----------
    confounds_raw : Pandas Dataframe or path to tsv file(s), optionally as a list.
        Raw confounds from fmriprep

    Returns
    -------
    conf :  a Confounds object
        conf.confounds_ is a reduced version of fMRIprep confounds.

    """

    def __init__(self):
        self.strategy = ["high_pass", "motion"]
        self.motion = "basic"
        self.n_motion = 0


class P9(Confounds):
    """
    Load confounds using the 9P strategy from Ciric et al. 2017.
    Basic motion parameters, WM/CSF signals, global signal and high pass filter.

    Parameters
    ----------
    confounds_raw : Pandas Dataframe or path to tsv file(s), optionally as a list.
        Raw confounds from fmriprep

    Returns
    -------
    conf :  a Confounds object
        conf.confounds_ is a reduced version of fMRIprep confounds.

    """

    def __init__(self):
        self.strategy = ["high_pass", "motion", "wm_csf", "global"]
        self.motion = "basic"
        self.n_motion = 0
        self.wm_csf = "basic"
        self.global_signal = "basic"


class P24(Confounds):
    """
    Load confounds using the 24P strategy from Ciric et al. 2017.
    Full motion parameters (derivatives, squares and squared derivatives),
    with high pass filter.

    Parameters
    ----------
    confounds_raw : Pandas Dataframe or path to tsv file(s), optionally as a list.
        Raw confounds from fmriprep

    Returns
    -------
    conf :  a Confounds object
        conf.confounds_ is a reduced version of fMRIprep confounds.

    """

    def __init__(self):
        self.strategy = ["high_pass", "motion"]
        self.motion = "full"
        self.n_motion = 0


class P36(Confounds):
    """
    Load confounds using the 36P strategy from Ciric et al. 2017.
    Motion parameters, WM/CSF signals, global signal, high pass filter.
    All noise components are fully expanded (derivatives, squares and squared
    derivatives).

    Parameters
    ----------
    confounds_raw : Pandas Dataframe or path to tsv file(s), optionally as a list.
        Raw confounds from fmriprep

    Returns
    -------
    conf :  a Confounds object
        conf.confounds_ is a reduced version of fMRIprep confounds.

    """

    def __init__(self):
        self.strategy = ["high_pass", "motion", "wm_csf", "global"]
        self.motion = "full"
        self.n_motion = 0
        self.wm_csf = "full"
        self.global_signal = "full"
