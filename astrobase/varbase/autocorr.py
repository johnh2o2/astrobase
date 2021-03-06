#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''autocorr.py - Waqas Bhatti (wbhatti@astro.princeton.edu) - Jan 2017

Calculates the autocorrelation for magnitude time series.

'''


from numpy import nan as npnan, sum as npsum, abs as npabs, \
    roll as nproll, isfinite as npisfinite, std as npstd, \
    sign as npsign, sqrt as npsqrt, median as npmedian, \
    array as nparray, percentile as nppercentile, \
    polyfit as nppolyfit, var as npvar, max as npmax, min as npmin, \
    log10 as nplog10, arange as nparange, pi as MPI, floor as npfloor, \
    argsort as npargsort, cos as npcos, sin as npsin, tan as nptan, \
    where as npwhere, linspace as nplinspace, \
    zeros_like as npzeros_like, full_like as npfull_like, all as npall, \
    correlate as npcorrelate, nonzero as npnonzero, diff as npdiff, \
    sort as npsort, ceil as npceil, int64 as npint64

from ..lcmath import sigclip_magseries, fill_magseries_gaps

#####################
## AUTOCORRELATION ##
#####################

def _autocorr_func1(mags, lag, maglen, magmed, magstd):
    '''Calculates the autocorr of mag series for specific lag.

    mags MUST be an array with no nans.

    lag is the current lag to calculate the autocorr for. MUST be less than the
    total number of observations in mags (maglen).

    maglen, magmed, magstd are provided by auto_correlation below.

    This version of the function taken from:

    doi:10.1088/0004-637X/735/2/68 (Kim et al. 2011)

    '''

    lagindex = nparange(1,maglen-lag)
    products = (mags[lagindex] - magmed) * (mags[lagindex+lag] - magmed)
    acorr = (1.0/((maglen - lag)*magstd)) * npsum(products)

    return acorr



def _autocorr_func2(mags, lag, maglen, magmed, magstd):
    '''
    This is an alternative function to calculate the autocorrelation.

    mags MUST be an array with no nans.

    lag is the current lag to calculate the autocorr for. MUST be less than the
    total number of observations in mags (maglen).

    maglen, magmed, magstd are provided by auto_correlation below.

    This version is from (first definition):

    https://en.wikipedia.org/wiki/Correlogram#Estimation_of_autocorrelations

    '''

    lagindex = nparange(0,maglen-lag)
    products = (mags[lagindex] - magmed) * (mags[lagindex+lag] - magmed)

    autocovarfunc = npsum(products)/lagindex.size
    varfunc = npsum((mags[lagindex] - magmed)*(mags[lagindex] - magmed))/mags.size

    acorr = autocovarfunc/varfunc

    return acorr



def _autocorr_func3(mags, lag, maglen, magmed, magstd):
    '''
    This is yet another alternative to calculate the autocorrelation.

    Stolen from:

    http://nbviewer.jupyter.org/github/CamDavidsonPilon/
    Probabilistic-Programming-and-Bayesian-Methods-for-Hackers/
    blob/master/Chapter3_MCMC/Chapter3.ipynb#Autocorrelation

    '''

    # from http://tinyurl.com/afz57c4
    result = npcorrelate(mags, mags, mode='full')
    result = result / npmax(result)
    return result[int(result.size / 2):]



def autocorr_magseries(times, mags, errs,
                       maxlags=1000,
                       func=_autocorr_func3,
                       fillgaps=0.0,
                       forcetimebin=None,
                       sigclip=3.0,
                       magsarefluxes=False,
                       filterwindow=11,
                       verbose=True):
    '''This calculates the ACF of a light curve.

    This will pre-process the light curve to fill in all the gaps and normalize
    everything to zero. If fillgaps == 'noiselevel', fills the gaps with the
    noise level obtained via the procedure above. If fillgaps == 'nan', fills
    the gaps with np.nan.

    '''

    # get the gap-filled timeseries
    interpolated = fill_magseries_gaps(times, mags, errs,
                                       fillgaps=fillgaps,
                                       forcetimebin=forcetimebin,
                                       sigclip=sigclip,
                                       magsarefluxes=magsarefluxes,
                                       filterwindow=filterwindow,
                                       verbose=verbose)

    if not interpolated:
        LOGERROR('failed to interpolate light curve to minimum cadence!')
        return None

    itimes, imags, ierrs = (interpolated['itimes'],
                            interpolated['imags'],
                            interpolated['ierrs'])

    # calculate the lags up to maxlags
    if maxlags:
        lags = nparange(0, maxlags)
    else:
        lags = nparange(itimes.size)

    series_stdev = 1.483*npmedian(npabs(imags))

    if func != _autocorr_func3:

        # get the autocorrelation as a function of the lag of the mag series
        autocorr = nparray([func(imags, x, imags.size, 0.0, series_stdev)
                            for x in lags])

    # this doesn't need a lags array
    else:

        autocorr = _autocorr_func3(imags, lags[0], imags.size,
                                   0.0, series_stdev)

    interpolated.update({'minitime':itimes.min(),
                         'lags':lags,
                         'acf':autocorr})

    return interpolated
