# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""
This module provides a class for principal components analysis (PCA).

PCA is an orthonormal, linear transform (i.e., a rotation) that maps the
data to a new coordinate system such that the maximal variability of the
data lies on the first coordinate (or the first principal component), the
second greatest variability is projected onto the second coordinate, and
so on.  The resulting data has unit covariance (i.e., it is decorrelated).
This technique can be used to reduce the dimensionality of the data.

More specifically, the data is projected onto the eigenvectors of the
covariance matrix.
"""

import sys

import numpy as np
import scipy.linalg as spl

from ...core.image.image import rollaxis as image_rollaxis
from ...core.reference.coordinate_map import drop_io_dim, AxisError


def pca(data, axis=0, mask=None, ncomp=None, standardize=True,
        design_keep=None, design_resid='mean', tol_ratio=0.01):
    """Compute the SVD PCA of an array-like thing over `axis`.

    Parameters
    ----------
    data : ndarray-like (np.float)
       The array on which to perform PCA over axis `axis` (below)
    axis : int, optional
       The axis over which to perform PCA (axis identifying
       observations).  Default is 0 (first)
    mask : ndarray-like (np.bool), optional
       An optional mask, should have shape given by data axes, with
       `axis` removed, i.e.: ``s = data.shape; s.pop(axis);
       msk_shape=s``
    ncomp : {None, int}, optional
       How many component basis projections to return. If ncomp is None
       (the default) then the number of components is given by the
       calculated rank of the data, after applying `design_keep`,
       `design_resid` and `tol_ratio` below.  We always return all the
       basis vectors and percent variance for each component; `ncomp`
       refers only to the number of basis_projections returned.
    standardize : bool, optional
       If True, standardize so each time series (after application of
       `design_keep` and `design_resid`) has the same standard
       deviation, as calculated by the ``np.std`` function.
    design_keep : None or ndarray, optional
       Data is projected onto the column span of design_keep.
       None (default) equivalent to ``np.identity(data.shape[axis])``
    design_resid : str or None or ndarray, optional
       After projecting onto the column span of design_keep, data is
       projected perpendicular to the column span of this matrix.  If
       None, we do no such second projection.  If a string 'mean', then
       the mean of the data is removed, equivalent to passing a column
       vector matrix of 1s.
    tol_ratio : float, optional
       If ``XZ`` is the vector of singular values of the projection
       matrix from `design_keep` and `design_resid`, and S are the
       singular values of ``XZ``, then `tol_ratio` is the value used to
       calculate the effective rank of the projection of the design, as
       in ``rank = ((S / S.max) > tol_ratio).sum()``

    Returns
    -------
    results : dict
        $G$ is the number of non-trivial components found after applying
       `tol_ratio` to the projections of `design_keep` and
       `design_resid`.

       `results` has keys:

       * ``basis_vectors``: series over `axis`, shape (data.shape[axis], G) -
          the eigenvectors of the PCA
       * ``pcnt_var``: percent variance explained by component, shape
          (G,)
       * ``basis_projections``: PCA components, with components varying
          over axis `axis`; thus shape given by: ``s = list(data.shape);
          s[axis] = ncomp``
       * ``axis``: axis over which PCA has been performed.

    Notes
    -----
    See ``pca_image.m`` from ``fmristat`` for Keith Worsley's code on
    which some of this is based.

    See: http://en.wikipedia.org/wiki/Principal_component_analysis for
    some inspiration for naming - particularly 'basis_vectors' and
    'basis_projections'
    """
    data = np.asarray(data)
    # We roll the PCA axis to be first, for convenience
    if axis is None:
        raise ValueError('axis cannot be None')
    data = np.rollaxis(data, axis)
    if mask is not None:
        mask = np.asarray(mask)
    if design_resid == 'mean':
        # equivalent to: design_resid = np.ones((data.shape[0], 1))
        def project_resid(Y):
            return Y - Y.mean(0)[None,...]
    elif design_resid is None:
        def project_resid(Y): return Y
    else: # matrix passed, we hope
        projector = np.dot(design_resid, spl.pinv(design_resid))
        def project_resid(Y):
            return Y - np.dot(projector, Y)
    if standardize:
        def rmse_scales_func(std_source):
            # modifies array in place
            resid = project_resid(std_source)
            # root mean square of the residual
            rmse = np.sqrt(np.square(resid).sum(axis=0) / resid.shape[0])
            # positive 1/rmse
            return np.where(rmse<=0, 0, 1. / rmse)
    else:
        rmse_scales_func = None
    """
    Perform the computations needed for the PCA.  This stores the
    covariance/correlation matrix of the data in the attribute 'C'.  The
    components are stored as the attributes 'components', for an fMRI
    image these are the time series explaining the most variance.

    Now, we compute projection matrices. First, data is projected onto
    the columnspace of design_keep, then it is projected perpendicular
    to column space of design_resid.
    """
    if design_keep is None:
        X = np.eye(data.shape[0])
    else:
        X = np.dot(design_keep, spl.pinv(design_keep))
    XZ = project_resid(X)
    UX, SX, VX = spl.svd(XZ, full_matrices=0)
    # The matrix UX has orthonormal columns and represents the
    # final "column space" that the data will be projected onto.
    rank = (SX/SX.max() > tol_ratio).sum()
    UX = UX[:,:rank].T
    # calculate covariance matrix in full-rank column space.  The returned
    # array is roughly: YX = dot(UX, data); C = dot(YX, YX.T), perhaps where the
    # data has been standarized, perhaps summed over slices
    C_full_rank  = _get_covariance(data, UX, rmse_scales_func, mask)
    # find the eigenvalues D and eigenvectors Vs of the covariance
    # matrix
    D, Vs = spl.eigh(C_full_rank)
    # Compute basis vectors in original column space
    basis_vectors = np.dot(UX.T, Vs).T
    # sort both in descending order of eigenvalues
    order = np.argsort(-D)
    D = D[order]
    basis_vectors = basis_vectors[order]
    pcntvar = D * 100 / D.sum()
    """
    Output the component basis_projections
    """
    if ncomp is None:
        ncomp = rank
    subVX = basis_vectors[:ncomp]
    out = _get_basis_projections(data, subVX, rmse_scales_func)
    # Roll PCA image axis back to original position in data array
    if axis < 0:
        axis += data.ndim
    out = np.rollaxis(out, 0, axis+1)
    return {'basis_vectors': basis_vectors.T,
            'pcnt_var': pcntvar,
            'basis_projections': out,
            'axis': axis}


def _get_covariance(data, UX, rmse_scales_func, mask):
    # number of points in PCA dimension
    rank, n_pts = UX.shape
    C = np.zeros((rank, rank))
    # loop over next dimension to save memory
    if data.ndim == 2:
        # If we have 2D data, just do the covariance all in one shot, by using
        # a slice that is the equivalent of the ':' slice syntax
        slices = [slice(None)]
    else:
        # If we have more then 2D, then we iterate over slices in the second
        # dimension, in order to save memory
        slices = [slice(i,i+1) for i in range(data.shape[1])]
    for i, s_slice in enumerate(slices):
        Y = data[:,s_slice].reshape((n_pts, -1))
        # project data into required space
        YX = np.dot(UX, Y)
        if rmse_scales_func is not None:
            YX *= rmse_scales_func(Y)
        if mask is not None:
            # weight data with mask.  Usually the weights will be 0,1
            YX = YX * np.nan_to_num(mask[s_slice].reshape(Y.shape[1]))
        C += np.dot(YX, YX.T)
    return C


def _get_basis_projections(data, subVX, rmse_scales_func):
    ncomp = subVX.shape[0]
    out = np.empty((ncomp,) + data.shape[1:], np.float)
    for i in range(data.shape[1]):
        Y = data[:,i].reshape((data.shape[0], -1))
        U = np.dot(subVX, Y)
        if rmse_scales_func is not None:
            U *= rmse_scales_func(Y)
        U.shape = (U.shape[0],) + data.shape[2:]
        out[:,i] = U
    return out


def pca_image(img, axis='t', mask=None, ncomp=None, standardize=True,
              design_keep=None, design_resid='mean', tol_ratio=0.01):
    """ Compute the PCA of an image over a specified axis

    Parameters
    ----------
    img : Image
        The image on which to perform PCA over the given `axis`
    axis : str or int
        Axis over which to perform PCA. Default is 't'. If `axis` is an integer,
        gives the index of the input (domain) axis of `img`. If `axis` is a str, can be
        an input (domain) name, or an output (range) name, that maps to an input
        (domain) name.
    mask : Image, optional
        An optional mask, should have shape == image.shape[:3] and the same
        coordinate map as `img` but with `axis` dropped
    ncomp : {None, int}, optional
       How many component basis projections to return. If ncomp is None
       (the default) then the number of components is given by the
       calculated rank of the data, after applying `design_keep`,
       `design_resid` and `tol_ratio` below.  We always return all the
       basis vectors and percent variance for each component; `ncomp`
       refers only to the number of basis_projections returned.
    standardize : bool, optional
       If True, standardize so each time series (after application of
       `design_keep` and `design_resid`) has the same standard
       deviation, as calculated by the ``np.std`` function.
    design_keep : None or ndarray, optional
       Data is projected onto the column span of design_keep.
       None (default) equivalent to ``np.identity(data.shape[axis])``
    design_resid : str or None or ndarray, optional
       After projecting onto the column span of design_keep, data is
       projected perpendicular to the column span of this matrix.  If
       None, we do no such second projection.  If a string 'mean', then
       the mean of the data is removed, equivalent to passing a column
       vector matrix of 1s.
    tol_ratio : float, optional
       If ``XZ`` is the vector of singular values of the projection
       matrix from `design_keep` and `design_resid`, and S are the
       singular values of ``XZ``, then `tol_ratio` is the value used to
       calculate the effective rank of the projection of the design, as
       in ``rank = ((S / S.max) > tol_ratio).sum()``

    Returns
    -------
    results : dict
        $L$ is the number of non-trivial components found after applying
       `tol_ratio` to the projections of `design_keep` and
       `design_resid`.

       `results` has keys:
       * ``basis_vectors``: series over `axis`, shape (data.shape[axis], L) -
          the eigenvectors of the PCA
       * ``pcnt_var``: percent variance explained by component, shape
          (L,)
       * ``basis_projections``: PCA components, with components varying
          over axis `axis`; thus shape given by: ``s = list(data.shape);
          s[axis] = ncomp``
       * ``axis``: axis over which PCA has been performed.
    """
    img_klass = img.__class__
    # Coordmap after dropping the axis over which we are going to PCA.  This has
    # the side effect of testing if the output axes are going to make sense if
    # we drop the intended axis
    try:
        dropped_cmap = drop_io_dim(img.coordmap, axis)
    except AxisError:
        err = sys.exc_info()[1]
        raise AxisError('Cannot do image PCA over axis %s because: %s' %
                        (axis, err))
    # Which axes did we drop? (the input `axis` could be an input or an output
    # axis name, or an input axis index)
    in_name = set(img.axes.coord_names).difference(
        dropped_cmap.function_domain.coord_names).pop()
    out_name = set(img.reference.coord_names).difference(
        dropped_cmap.function_range.coord_names).pop()
    # Roll the chosen axis to input position zero
    work_img = image_rollaxis(img, axis)
    if mask is not None:
        if not mask.coordmap.similar_to(dropped_cmap):
            raise ValueError("Mask should have matching coordmap to `img` "
                             "coordmap with dropped axis %s" % axis)
    data = work_img.get_data()
    if mask is not None:
        mask_data = mask.get_data()
    else:
        mask_data = None
    # do the PCA
    res = pca(data, 0, mask_data, ncomp, standardize,
              design_keep, design_resid, tol_ratio)
    # Clean up images after PCA
    # Rename the axis we dropped
    output_coordmap = work_img.coordmap.renamed_domain(
        {in_name: 'PCA components'})
    # And the matching output axis
    output_coordmap = output_coordmap.renamed_range(
        {out_name: 'PCA components'})
    output_img = img_klass(res['basis_projections'], output_coordmap)
    # We have to roll the axis back to the original position
    roll_index = img.axes.index(in_name)
    output_img = image_rollaxis(output_img, roll_index, inverse=True)
    key = 'basis_vectors over %s' % axis
    res[key] = res['basis_vectors']
    res['basis_projections'] = output_img
    return res