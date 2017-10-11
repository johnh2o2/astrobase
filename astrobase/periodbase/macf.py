#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''macf.py - Waqas Bhatti (wbhatti@astro.princeton.edu) - Oct 2017

This contains the ACF period-finding algorithm from McQuillian+ 2013a and
McQuillian+ 2014.

'''


from multiprocessing import Pool, cpu_count
import logging
from datetime import datetime
from traceback import format_exc

import numpy as np

# import these to avoid lookup overhead
from numpy import nan as npnan, sum as npsum, abs as npabs, \
    roll as nproll, isfinite as npisfinite, std as npstd, \
    sign as npsign, sqrt as npsqrt, median as npmedian, \
    array as nparray, percentile as nppercentile, \
    polyfit as nppolyfit, var as npvar, max as npmax, min as npmin, \
    log10 as nplog10, arange as nparange, pi as MPI, floor as npfloor, \
    argsort as npargsort, cos as npcos, sin as npsin, tan as nptan, \
    where as npwhere, linspace as nplinspace, \
    zeros_like as npzeros_like, full_like as npfull_like, \
    arctan as nparctan, nanargmax as npnanargmax, nanargmin as npnanargmin, \
    empty as npempty, ceil as npceil, mean as npmean, \
    digitize as npdigitize, unique as npunique, \
    argmax as npargmax, argmin as npargmin

from scipy.signal import argrelmax, argrelmin, savgol_filter
from astropy.convolution import convolve, Gaussian1DKernel


#############
## LOGGING ##
#############

# setup a logger
LOGGER = None

def set_logger_parent(parent_name):
    globals()['LOGGER'] = logging.getLogger('%s.macf' % parent_name)

def LOGDEBUG(message):
    if LOGGER:
        LOGGER.debug(message)
    elif DEBUG:
        print('%sZ [DBUG]: %s' % (datetime.utcnow().isoformat(), message))

def LOGINFO(message):
    if LOGGER:
        LOGGER.info(message)
    else:
        print('%sZ [INFO]: %s' % (datetime.utcnow().isoformat(), message))

def LOGERROR(message):
    if LOGGER:
        LOGGER.error(message)
    else:
        print('%sZ [ERR!]: %s' % (datetime.utcnow().isoformat(), message))

def LOGWARNING(message):
    if LOGGER:
        LOGGER.warning(message)
    else:
        print('%sZ [WRN!]: %s' % (datetime.utcnow().isoformat(), message))

def LOGEXCEPTION(message):
    if LOGGER:
        LOGGER.exception(message)
    else:
        print(
            '%sZ [EXC!]: %s\nexception was: %s' % (
                datetime.utcnow().isoformat(),
                message, format_exc()
                )
            )


###################
## LOCAL IMPORTS ##
###################

from ..lcmath import phase_magseries, sigclip_magseries, time_bin_magseries, \
    phase_bin_magseries, fill_magseries_gaps

from ..varbase.autocorr import autocorr_magseries


############
## CONFIG ##
############

NCPUS = cpu_count()



######################
## HELPER FUNCTIONS ##
######################


def _smooth_acf(acf, windowfwhm=7, windowsize=21):
    '''
    This returns a smoothed version of the ACF.

    Convolves the ACF with a Gaussian of given windowsize and windowfwhm

    '''

    convkernel = Gaussian1DKernel(windowfwhm, x_size=windowsize)
    smoothed = convolve(acf, convkernel, boundary='extend')

    return smoothed


def _smooth_acf_savgol(acf, windowsize=21, polyorder=2):
    '''
    This returns a smoothed version of the ACF.

    This version uses the Savitsky-Golay smoothing filter

    '''

    smoothed = savgol_filter(acf, windowsize, polyorder)

    return smoothed



def _get_acf_peakheights(lags, acf, npeaks=20, searchinterval=1):
    '''This calculates the relative peak heights for first npeaks in ACF.

    Usually, the first peak or the second peak (if its peak height > first peak)
    corresponds to the correct lag. When we know the correct lag, the period is
    then:

    bestperiod = time[lags == bestlag] - time[0]

    '''

    maxinds = argrelmax(acf, order=searchinterval)[0]
    maxacfs = acf[maxinds]
    maxlags = lags[maxinds]
    mininds = argrelmin(acf, order=searchinterval)[0]
    minacfs = acf[mininds]
    minlags = lags[mininds]

    relpeakheights = np.zeros(npeaks)
    relpeaklags = np.zeros(npeaks,dtype=np.int64)
    peakindices = np.zeros(npeaks,dtype=np.int64)

    for peakind, mxi in enumerate(maxinds[:npeaks]):

        leftminind = mininds[mininds < mxi][-1] # the last index to the left
        rightminind = mininds[mininds > mxi][0] # the first index to the right
        relpeakheights[peakind] = (
            acf[mxi] - (acf[leftminind] + acf[rightminind])/2.0
        )
        relpeaklags[peakind] = lags[mxi]
        peakindices[peakind] = peakind

    # figure out the bestperiod if possible
    if relpeakheights[0] > relpeakheights[1]:
        bestlag = relpeaklags[0]
        bestpeakheight = relpeakheights[0]
        bestpeakindex = peakindices[0]
    else:
        bestlag = relpeaklags[1]
        bestpeakheight = relpeakheights[1]
        bestpeakindex = peakindices[1]

    return {'maxinds':maxinds,
            'maxacfs':maxacfs,
            'maxlags':maxlags,
            'mininds':mininds,
            'minacfs':minacfs,
            'minlags':minlags,
            'relpeakheights':relpeakheights,
            'relpeaklags':relpeaklags,
            'peakindices':peakindices,
            'bestlag':bestlag,
            'bestpeakheight':bestpeakheight,
            'bestpeakindex':bestpeakindex}


############################
## PERIOD FINDER FUNCTION ##
############################

def macf_period_find(
        times,
        mags,
        errs,
        maxlags=None,
        maxacfpeaks=10,
        fillgaps=0.0,
        forcetimebin=None,
        filterwindow=11,
        smoothacf=21,
        smoothfunc=_smooth_acf_savgol,
        smoothfunckwargs={},
        magsarefluxes=False,
        sigclip=3.0,
        verbose=True
):
    '''This finds periods using the McQuillian+ (2013a, 2014) method.

    If smoothacf is not None, will smooth ACF using the given smoothing window
    FWHM.

    '''

    # get the ACF
    acfres = autocorr_magseries(
        times,
        mags,
        errs,
        maxlags=maxlags,
        fillgaps=fillgaps,
        forcetimebin=forcetimebin,
        sigclip=sigclip,
        magsarefluxes=magsarefluxes,
        filterwindow=filterwindow,
        verbose=verbose
    )

    xlags = acfres['lags']

    # smooth the ACF if requested
    if smoothacf and isinstance(smoothacf, int) and smoothacf > 0:

        smoothfunckwargs.update({'windowsize':smoothacf})
        xacf = smoothfunc(acfres['acf'], **smoothfunckwargs)

    else:

        xacf = acfres['acf']


    # get the relative peak heights and fit best lag
    peakres = _get_acf_peakheights(xlags, xacf, npeaks=maxacfpeaks,
                                   searchinterval=int(smoothacf/2))

    # this is the best period's best ACF peak height
    bestlspval = peakres['bestpeakheight']

    try:

        # get the fit best lag from a linear fit to the peak index vs time(peak
        # lag) function as in McQillian+ (2014)
        fity = np.concatenate((
            [0.0, peakres['bestlag']],
            peakres['relpeaklags'][peakres['relpeaklags'] > peakres['bestlag']]
        ))
        fity = fity*acfres['cadence']
        fitx = np.arange(fity.size)

        fitcoeffs, fitcovar = np.polyfit(fitx, fity, 1, cov=True)

        # fit best period is the gradient of fit
        fitbestperiod = fitcoeffs[0]
        bestperiodrms = np.sqrt(fitcovar[0,0]) # from the covariance matrix

    except:

        LOGWARNING('linear fit to time at each peak lag '
                   'value vs. peak number failed, '
                   'naively calculated ACF period may not be accurate')
        fitcoeffs = np.array([np.nan, np.nan])
        fitcovar = np.array([[np.nan, np.nan], [np.nan, np.nan]])
        fitbestperiod = np.nan
        bestperiodrms = np.nan
        raise

    # calculate the naive best period using delta_tau = lag * cadence
    naivebestperiod = peakres['bestlag']*acfres['cadence']

    if fitbestperiod < naivebestperiod:
        LOGWARNING('fit bestperiod = %.5f may be an alias, '
                   'naively calculated bestperiod is = %.5f' %
                   (fitbestperiod, naivebestperiod))

    if np.isfinite(fitbestperiod):
        bestperiod = fitbestperiod
    else:
        bestperiod = naivebestperiod


    return {'bestperiod':bestperiod,
            'bestlspval':bestlspval,
            'nbestpeaks':maxacfpeaks,
            'lspvals':xacf,
            'periods':xlags*acfres['cadence'],
            'acf':xacf,
            'lags':xlags,
            'method':'acf',
            'naivebestperiod':naivebestperiod,
            'fitbestperiod':fitbestperiod,
            'fitperiodrms':bestperiodrms,
            'periodfitcoeffs':fitcoeffs,
            'periodfitcovar':fitcovar,
            'kwargs':{'maxlags':maxlags,
                      'maxacfpeaks':maxacfpeaks,
                      'fillgaps':fillgaps,
                      'filterwindow':filterwindow,
                      'smoothacf':smoothacf,
                      'smoothfunckwargs':smoothfunckwargs,
                      'magsarefluxes':magsarefluxes,
                      'sigclip':sigclip},
            'acfresults':acfres,
            'acfpeaks':peakres}