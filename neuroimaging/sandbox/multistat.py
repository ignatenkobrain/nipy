"""
FIXME: This module is pretty heavily broken. It's been moved here to the
sandbox as an act of triage. If we want it we can clean it up and put it back
into fmri.fmristat or we can decide to scrap it, which should be Jonathan
Taylor's call.
"""
import numpy as N
import numpy.linalg as L
from scipy.sandbox.models.utils import recipr, rank

from neuroimaging.core.api import Image


class RFXMean(object):
    """
    Perform a RFX analysis for the mean -- i.e. the fixed effect design matrix is a column of 1's.

    Input is a sequence: if the entries are 
    """

    def __init__(self, input, df=None, fwhm=None, tol=1.0e+05, outputs=None,
                 clobber=False, max_varatio=10., df_limit=4., df_target=100.,
                 niter=10, verbose=False, fixed=False, mask=None,
                 fwhm_varatio=None, **keywords):

        self.clobber = clobber
        self.max_varatio = max_varatio
        self.df_limit = df_limit
        self.df_target = df_target
        self.niter = niter
        self.verbose = verbose
        self.fixed = fixed
        self.mask = mask
        self.fwhm_varatio = fwhm_varatio

        self.nsubject = len(input_files)

        self.X = N.ones((self.nsubject, 1))
        self.Xsq = N.power(self.design_matrix.T, 2)
        self.pinvX = L.pinv(self.X)

        # Prepare files for reading in

        self.input = []
        if sd_files:
            if len(sd_files) != len(input_files):
                raise ValueError, 'expecting the same number of SD files as input files in MultiStat'
            self.sd = []

        for subject in range(self.nsubject):
            self.input.append(iter(Image(input_files[subject], **keywords)))
            if sd_files:
                self.sd.append(iter(Image(sd_files[subject], **keywords)))
    
        resid_files = {}

    def _df(self):
        """
        Work out degrees of freedom from input.
        """

        npred = rank(self.X)

        self.df_resid = self.nsubject - npred

        if self.df_resid > 0:
            if sd_files:
                try:
                    if (len(df) != len(input_files)):
                        raise ValueError, 'len(df) != len(input_files) in MultiStat'
                    self.input_df = array(list(df))
                except TypeError:
                    self.input_df = N.ones((len(input_files),)) * df
            else:
                self.input_df = N.inf * N.ones((len(input_files),))

        self.df_fixed = N.add.reduce(self.input_df)
    
        self.df_target = df_target
        if not fixed:
            if fwhm:
                self.input_fwhm = fwhm
            else:
                self.fwhmraw = iter(iterFWHM(self.template, df_resid=self.df_resid, fwhm=fwhmfile, resels=reselsfile, mask=fwhmmask))
        else:
            self.input_fwhm = 6.0
                

    def estimate_varatio(self, Y, S=None, df=None):

        self.Y = N.zeros((self.nsubject, self.npixel))
        self.S = N.ones((self.nsubject, self.npixel))

    def fit(self, Y, S=None, df=None):

        if not self.fixed and self.varatio is None:
            self.estimate_varatio(Y, S, df)
            
        effect = N.zeros(Y.shape[1:])
        sdeffect = N.zeros(Y.shape[1:])

        ncpinvX = N.sqrt(N.add.reduce(N.power(N.squeeze(self.pinvX), 2)))
   
        sigma2 = self.varfix * self.varatio

        Sigma = self.S + multiply.outer(N.ones((self.nsubject,)), sigma2)

        # To ensure that Sigma is always positive:
        if self.fwhm_varatio > 0:
            Sigma = maximum(Sigma, self.S * 0.25)

        W = recipr(Sigma)
        X2W = N.dot(self.Xsq, W)
        XWXinv = recipr(X2W)
        betahat = XWXinv * N.dot(self.X.T, W * self.Y)
        sdeffect = N.dot(self.contrast, sqrt(XWXinv)).T
    
        betahat = N.dot(self.pinvX, self.Y)
        varatio_smooth = self.varatio_smooth.next()
        varatio_smooth.setshape(product(varatio_smooth.shape))
        sigma2 = varatio_smooth.T
        sdeffect = ncpinvX * sqrt(sigma2.T)
        Sigma = N.dot(N.one((self.nsubject,)), sigma2)
        W = recipr(Sigma)
        effect = N.dot(self.contrast, betahat).T

        tstat = effect * recipr(sdeffect)


