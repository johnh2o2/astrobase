#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''trilegal - Waqas Bhatti (wbhatti@astro.princeton.edu) - Dec 2017
License: MIT. See the LICENSE file for more details.

This downloads and interacts with galaxy models generated by the TRILEGAL
web-form by Prof. Leo Girardi. This module requires the `requests` and `astropy`
packages only and can be used without astrobase if the accompanying `dust.py`
module is located in the same directory as this module.

If you use this, please cite the TRILEGAL papers:

http://stev.oapd.inaf.it/~webmaster/trilegal_1.6/papers.html

and link to the TRILEGAL website:

http://stev.oapd.inaf.it/cgi-bin/trilegal

The extinction coefficient Av_at_infinity for the requested coordinates is
automatically obtained from the 2MASS DUST service at:

http://irsa.ipac.caltech.edu/applications/DUST/

'''
import os
import os.path
import gzip
import hashlib
import time
import logging
from datetime import datetime
from traceback import format_exc
import re

import numpy as np

# to do the queries
import requests
import requests.exceptions

# to convert to/from galactic coords
from astropy.coordinates import SkyCoord
from astropy import units as u



#############
## LOGGING ##
#############

# setup a logger
LOGGER = None

def set_logger_parent(parent_name):
    globals()['LOGGER'] = logging.getLogger('%s.trilegal' % parent_name)

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

from . import dust


############################
## TRILEGAL FORM SETTINGS ##
############################

# URL of the POST form target
TRILEGAL_POSTURL = 'http://stev.oapd.inaf.it/cgi-bin/trilegal_{formversion}'

# BASE URL for the results
TRILEGAL_BASEURL = 'http://stev.oapd.inaf.it'

# regex to get the result file name
TRILEGAL_REGEX = re.compile('a href\S*.dat')

# these are the params that the user will probably interact with the most
TRILEGAL_INPUT_PARAMS = {
    'binary_kind':'1',
    'extinction_infty':'0.0398',
    'extinction_sigma':'0.1',
    'gc_b':'60.0',
    'gc_l':'90.0',
    'field':'1.0',
    'icm_lim':'4',
    'mag_lim':'26.0',
    'photsys_file':'tab_mag_odfnew/tab_mag_sloan_2mass.dat',
    'trilegal_version':'1.6',
}

# these are taken from get_trilegal.pm, a Perl script from Prof. Leo Girardi
# a version of this is at T. D. Morton's VESPA github repository:
# https://github.com/timothydmorton/VESPA/blob/master/scripts/get_trilegal
TRILEGAL_DEFAULT_PARAMS = {
    'binary_frac': '0.3',
    'binary_kind': '${use_binaries}',
    'binary_mrinf': '0.7',
    'binary_mrsup': '1',
    'bulge_a': '1',
    'bulge_a0': '95',
    'bulge_am': '2500',
    'bulge_b': '-2.0e9',
    'bulge_csi': '0.31',
    'bulge_cutoffmass': '0.01',
    'bulge_eta': '0.68',
    'bulge_file': 'tab_sfr/file_sfr_bulge_zoccali_p03.dat',
    'bulge_kind': '2',
    'bulge_phi0': '15',
    'bulge_rho_central': '406.0',
    'eq_alpha': '0',
    'eq_delta': '0',
    'extinction_h_r': '100000',
    'extinction_h_z': '110',
    'extinction_infty': '${avextinction}',
    'extinction_kind': '2',
    'extinction_rho_sun': '0.00015',
    'extinction_sigma': '${sigmaav_av}',
    'field': '${area}',
    'gal_coord': '1', # 1 -> set to gl_deg, gb_deg, 2 -> set to ra_hr, decl_deg
    'gc_b': '${gal_b}',
    'gc_l': '${gal_l}',
    'halo_a': '1',
    'halo_b': '0',
    'halo_file': 'tab_sfr/file_sfr_halo.dat',
    'halo_kind': '2',
    'halo_q': '0.65',
    'halo_r_eff': '2800',
    'halo_rho_sun': '0.00015',
    'icm_lim': '${icmlim}',
    'imf_file': 'tab_imf/imf_chabrier_lognormal.dat',
    'mag_lim': '${maglim}',
    'mag_res': '0.1',
    'object_a': '1',
    'object_av': '1.504',
    'object_avkind': '1',
    'object_b': '0',
    'object_cutoffmass': '0.8',
    'object_dist': '1658',
    'object_file': 'tab_sfr/file_sfr_m4.dat',
    'object_kind': '0',
    'object_mass': '1280',
    'output_kind': '1',
    'photsys_file': 'tab_mag_odfnew/tab_mag_${system}.dat',
    'r_sun': '8700',
    'submit_form': 'Submit',
    'thickdisk_a': '1',
    'thickdisk_b': '0',
    'thickdisk_file': 'tab_sfr/file_sfr_thickdisk.dat',
    'thickdisk_h_r': '2800',
    'thickdisk_h_z': '800',
    'thickdisk_kind': '0',
    'thickdisk_r_max': '15000',
    'thickdisk_r_min': '0',
    'thickdisk_rho_sun': '0.0015',
    'thindisk_a': '0.8',
    'thindisk_b': '0',
    'thindisk_file': 'tab_sfr/file_sfr_thindisk_mod.dat',
    'thindisk_h_r': '2800',
    'thindisk_h_z0': '95',
    'thindisk_hz_alpha': '1.6666',
    'thindisk_hz_tau0': '4400000000',
    'thindisk_kind': '3',
    'thindisk_r_max': '15000',
    'thindisk_r_min': '0',
    'thindisk_rho_sun': '59',
    'trilegal_version': '${version}',
    'z_sun': '24.2'
}


# these were extracted from the TRILEGAL HTML form at:
# http://stev.oapd.inaf.it/cgi-bin/trilegal
TRILEGAL_FILTER_SYSTEMS = {
    '2mass': {
        'desc': '2MASS JHKs',
        'table': 'tab_mag_odfnew/tab_mag_2mass.dat'
    },
    '2mass_spitzer_wise': {
        'desc': '2MASS + Spitzer (IRAC+MIPS) + WISE',
        'table': 'tab_mag_odfnew/tab_mag_2mass_spitzer_wise.dat'
    },
    '2mass_spitzer_wise_washington_ddo51': {
        'desc': '2MASS+Spitzer+WISE+Washington+DDO51',
        'table': 'tab_mag_odfnew/tab_mag_2mass_spitzer_wise_washington_ddo51.dat'
    },
    'TESS_2mass_kepler': {
        'desc': ('TESS + 2MASS (Vegamags) + Kepler + SDSS griz + '
                 'DDO51 (in ABmags)'),
        'table': 'tab_mag_odfnew/tab_mag_TESS_2mass_kepler.dat'
    },
    'UVbright': {
        'desc': 'HST+GALEX+Swift/UVOT UV filters',
        'table': 'tab_mag_odfnew/tab_mag_UVbright.dat'
    },
    'acs_hrc': {
        'desc': 'HST/ACS HRC',
        'table': 'tab_mag_odfnew/tab_mag_acs_hrc.dat'
    },
    'acs_wfc': {
        'desc': 'HST/ACS WFC',
        'table': 'tab_mag_odfnew/tab_mag_acs_wfc.dat'
    },
    'akari': {
        'desc': 'AKARI',
        'table': 'tab_mag_odfnew/tab_mag_akari.dat'
    },
    'batc': {
        'desc': 'BATC',
        'table': 'tab_mag_odfnew/tab_mag_batc.dat'
    },
    'bessell': {
        'desc': 'UBVRIJHKLMN (cf. Bessell 1990 + Bessell & Brett 1988)',
        'table': 'tab_mag_odfnew/tab_mag_bessell.dat'
    },
    'ciber': {
        'desc': 'CIBER',
        'table': 'tab_mag_odfnew/tab_mag_ciber.dat'
    },
    'dcmc': {
        'desc': 'DCMC',
        'table': 'tab_mag_odfnew/tab_mag_dcmc.dat'
    },
    'decam': {
        'desc': 'DECAM (ABmags)',
        'table': 'tab_mag_odfnew/tab_mag_decam.dat'
    },
    'decam_vista': {
        'desc': 'DECAM ugrizY (ABmags) + VISTA ZYJHKs (Vegamags)',
        'table': 'tab_mag_odfnew/tab_mag_decam_vista.dat'
    },
    'denis': {
        'desc': 'DENIS',
        'table': 'tab_mag_odfnew/tab_mag_denis.dat'
    },
    'dmc14': {
        'desc': 'DMC 14 filters',
        'table': 'tab_mag_odfnew/tab_mag_dmc14.dat'
    },
    'dmc15': {
        'desc': 'DMC 15 filters',
        'table': 'tab_mag_odfnew/tab_mag_dmc15.dat'
    },
    'eis': {
        'desc': 'ESO/EIS (WFI UBVRIZ + SOFI JHK)',
        'table': 'tab_mag_odfnew/tab_mag_eis.dat'
    },
    'gaia': {
        'desc': "Gaia's G, G_BP and G_RP (Vegamags)",
        'table': 'tab_mag_odfnew/tab_mag_gaia.dat'
    },
    'galex': {
        'desc': "GALEX FUV+NUV (Vegamag) + Johnson's UBV",
        'table': 'tab_mag_odfnew/tab_mag_galex.dat'
    },
    'galex_sloan': {
        'desc': 'GALEX FUV+NUV + SDSS ugriz (all ABmags)',
        'table': 'tab_mag_odfnew/tab_mag_galex_sloan.dat'
    },
    'int_wfc': {
        'desc': 'INT/WFC (Vegamag)',
        'table': 'tab_mag_odfnew/tab_mag_int_wfc.dat'
    },
    'iphas': {
        'desc': 'IPHAS',
        'table': 'tab_mag_odfnew/tab_mag_iphas.dat'
    },
    'jwst_wide': {
        'desc': 'planned JWST wide filters',
        'table': 'tab_mag_odfnew/tab_mag_jwst_wide.dat'
    },
    'kepler': {
        'desc': 'Kepler + SDSS griz + DDO51 (in ABmags)',
        'table': 'tab_mag_odfnew/tab_mag_kepler.dat'
    },
    'kepler_2mass': {
        'desc': ('Kepler + SDSS griz + DDO51 (in ABmags) + 2MASS '
                 '(~Vegamag)'),
        'table': 'tab_mag_odfnew/tab_mag_kepler_2mass.dat'
    },
    'lbt_lbc': {
        'desc': 'LBT/LBC (Vegamag)',
        'table': 'tab_mag_odfnew/tab_mag_lbt_lbc.dat'
    },
    'lsst': {
        'desc': ('LSST ugrizY, March 2012 total filter throughputs (all '
                 'ABmags)'),
        'table': 'tab_mag_odfnew/tab_mag_lsst.dat'}
    ,
    'megacam': {
        'desc': "CFHT/Megacam u*g'r'i'z'",
        'table': 'tab_mag_odfnew/tab_mag_megacam.dat'
    },
    'megacam_wircam': {
        'desc': 'CFHT Megacam + Wircam (all ABmags)',
        'table': 'tab_mag_odfnew/tab_mag_megacam_wircam.dat'
    },
    'nicmosab': {
        'desc': 'HST/NICMOS AB',
        'table': 'tab_mag_odfnew/tab_mag_nicmosab.dat'
    },
    'nicmosst': {
        'desc': 'HST/NICMOS ST',
        'table': 'tab_mag_odfnew/tab_mag_nicmosst.dat'
    },
    'nicmosvega': {
        'desc': 'HST/NICMOS vega',
        'table': 'tab_mag_odfnew/tab_mag_nicmosvega.dat'
    },
    'noao_ctio_mosaic2': {
        'desc': 'NOAO/CTIO/MOSAIC2 (Vegamag)',
        'table': 'tab_mag_odfnew/tab_mag_noao_ctio_mosaic2.dat'
    },
    'ogle': {
        'desc': 'OGLE-II',
        'table': 'tab_mag_odfnew/tab_mag_ogle.dat'
    },
    'ogle_2mass_spitzer': {
        'desc': 'OGLE + 2MASS + Spitzer (IRAC+MIPS)',
        'table': 'tab_mag_odfnew/tab_mag_ogle_2mass_spitzer.dat'
    },
    'panstarrs1': {
        'desc': 'Pan-STARRS1',
        'table': 'tab_mag_odfnew/tab_mag_panstarrs1.dat'
    },
    'sloan': {
        'desc': 'SDSS ugriz',
        'table': 'tab_mag_odfnew/tab_mag_sloan.dat'
    },
    'sloan_2mass': {
        'desc': 'SDSS ugriz + 2MASS JHKs',
        'table': 'tab_mag_odfnew/tab_mag_sloan_2mass.dat'
    },
    'sloan_ukidss': {
        'desc': 'SDSS ugriz + UKIDSS ZYJHK',
        'table': 'tab_mag_odfnew/tab_mag_sloan_ukidss.dat'
    },
    'spitzer': {
        'desc': 'Spitzer IRAC+MIPS',
        'table': 'tab_mag_odfnew/tab_mag_spitzer.dat'
    },
    'stis': {
        'desc': 'HST/STIS imaging mode',
        'table': 'tab_mag_odfnew/tab_mag_stis.dat'
    },
    'stroemgren': {
        'desc': 'Stroemgren-Crawford',
        'table': 'tab_mag_odfnew/tab_mag_stroemgren.dat'
    },
    'suprimecam': {
        'desc': 'Subaru/Suprime-Cam (ABmags)',
        'table': 'tab_mag_odfnew/tab_mag_suprimecam.dat'
    },
    'swift_uvot': {
        'desc': 'SWIFT/UVOT UVW2, UVM2, UVW1,u (Vegamag)',
        'table': 'tab_mag_odfnew/tab_mag_swift_uvot.dat'
    },
    'tycho2': {
        'desc': 'Tycho VTBT',
        'table': 'tab_mag_odfnew/tab_mag_tycho2.dat'
    },
    'ubvrijhk': {
        'desc': 'UBVRIJHK (cf. Maiz-Apellaniz 2006 + Bessell 1990)',
        'table': 'tab_mag_odfnew/tab_mag_ubvrijhk.dat'
    },
    'ukidss': {
        'desc': 'UKIDSS ZYJHK (Vegamag)',
        'table': 'tab_mag_odfnew/tab_mag_ukidss.dat'
    },
    'vilnius': {
        'desc': 'Vilnius',
        'table': 'tab_mag_odfnew/tab_mag_vilnius.dat'
    },
    'visir': {
        'desc': 'VISIR',
        'table': 'tab_mag_odfnew/tab_mag_visir.dat'
    },
    'vista': {
        'desc': 'VISTA ZYJHKs (Vegamag)',
        'table': 'tab_mag_odfnew/tab_mag_vista.dat'
    },
    'vphas': {
        'desc': 'VPHAS+ (ABmags)',
        'table': 'tab_mag_odfnew/tab_mag_vphas.dat'
    },
    'vst_omegacam': {
        'desc': 'VST/OMEGACAM (ABmag)',
        'table': 'tab_mag_odfnew/tab_mag_vst_omegacam.dat'
    },
    'washington': {
        'desc': 'Washington CMT1T2',
        'table': 'tab_mag_odfnew/tab_mag_washington.dat'
    },
    'washington_ddo51': {
        'desc': 'Washington CMT1T2 + DDO51',
        'table': 'tab_mag_odfnew/tab_mag_washington_ddo51.dat'
    },
    'wfc3_medium': {
        'desc': ('HST/WFC3 medium filters (UVIS1+IR, final '
                 'throughputs)'),
        'table': 'tab_mag_odfnew/tab_mag_wfc3_medium.dat'
    },
    'wfc3_verywide': {
        'desc': ('HST/WFC3 long-pass and extremely wide filters '
                 '(UVIS1, final throughputs)'),
        'table': 'tab_mag_odfnew/tab_mag_wfc3_verywide.dat'
    },
    'wfc3_wide': {
        'desc': 'HST/WFC3 wide filters (UVIS1+IR, final throughputs)',
        'table': 'tab_mag_odfnew/tab_mag_wfc3_wide.dat'
    },
    'wfc3_wideverywide': {
        'desc': ('HST/WFC3 all W+LP+X filters (UVIS1+IR, final '
                 'throughputs)'),
        'table': 'tab_mag_odfnew/tab_mag_wfc3_wideverywide.dat'
    },
    'wfc3ir': {
        'desc': 'HST/WFC3 IR channel (final throughputs)',
        'table': 'tab_mag_odfnew/tab_mag_wfc3ir.dat'
    },
    'wfc3uvis1': {
        'desc': 'HST/WFC3 UVIS channel, chip 1 (final throughputs)',
        'table': 'tab_mag_odfnew/tab_mag_wfc3uvis1.dat'
    },
    'wfc3uvis2': {
        'desc': 'HST/WFC3 UVIS channel, chip 2 (final throughputs)',
        'table': 'tab_mag_odfnew/tab_mag_wfc3uvis2.dat'
    },
    'wfi': {
        'desc': 'ESO/WFI',
        'table': 'tab_mag_odfnew/tab_mag_wfi.dat'
    },
    'wfi2': {
        'desc': 'ESO/WFI2',
        'table': 'tab_mag_odfnew/tab_mag_wfi2.dat'
    },
    'wfi_sofi': {
        'desc': 'ESO/WFI+SOFI',
        'table': 'tab_mag_odfnew/tab_mag_wfi_sofi.dat'
    },
    'wfpc2': {
        'desc': 'HST/WFPC2 (Vegamag, cf. Holtzman et al. 1995)',
        'table': 'tab_mag_odfnew/tab_mag_wfpc2.dat'
    },
    'wircam': {
        'desc': 'CFHT Wircam',
        'table': 'tab_mag_odfnew/tab_mag_wircam.dat'
    }
}



##############################
## TRILEGAL QUERY FUNCTIONS ##
##############################

def list_trilegal_filtersystems():
    '''
    This just lists all the filter systems available for TRILEGAL.

    '''

    print('%-40s %s' % ('FILTER SYSTEM NAME','DESCRIPTION'))
    print('%-40s %s' % ('------------------','-----------'))
    for key in sorted(TRILEGAL_FILTER_SYSTEMS.keys()):
        print('%-40s %s' % (key, TRILEGAL_FILTER_SYSTEMS[key]['desc']))



def query_galcoords(gal_lon,
                    gal_lat,
                    filtersystem='sloan_2mass',
                    field_deg2=1.0,
                    usebinaries=True,
                    extinction_sigma=0.1,
                    magnitude_limit=26.0,
                    maglim_filtercol=4,
                    trilegal_version=1.6,
                    extraparams=None,
                    forcefetch=False,
                    cachedir='~/.astrobase/trilegal-cache',
                    verbose=True,
                    timeout=60.0,
                    refresh=150.0,
                    maxtimeout=700.0):
    '''This queries the TRILEGAL model form, downloads results, and parses them.

    gal_lon and gal_lat are galactic longitude and latitude in degrees.

    filtersystem is a key in the TRILEGAL_FILTER_SYSTEMS dict. Use the function
    trilegal.list_trilegal_filtersystems() to see a nicely formatted table with
    the key and description for each of these.

    field_deg2 is the area of the simulated field in degrees.

    If usebinaries is True, binaries will be present in the model results.

    extinction_sigma is the applied std dev around the Av_extinction value for
    the galactic coordinates requested.

    magnitude_limit is the limiting magnitude of the simulation in the
    maglim_filtercol-th band of the filter system chosen.

    trilegal_version is the version of the TRILEGAL form to use. This can
    usually left as-is.

    extraparams is a dict that can be used to override parameters of the model
    other than the basic ones used for input to this function. All parameters
    are listed in TRILEGAL_DEFAULT_PARAMS. See:

    http://stev.oapd.inaf.it/cgi-bin/trilegal

    for explanations of these parameters.

    If forcefetch is True, the query will be retried even if cached results for
    it exist.

    cachedir points to the directory where results will be downloaded.

    timeout sets the amount of time in seconds to wait for the service to
    respond to our initial form submission.

    refresh sets the amount of time in seconds to wait before checking if the
    result file is available. If the results file isn't available after refresh
    seconds have elapsed, the function will wait for refresh continuously, until
    maxtimeout is reached or the results file becomes available.

    '''

    # these are the default parameters
    inputparams = TRILEGAL_INPUT_PARAMS.copy()

    # update them with the input params
    inputparams['binary_kind'] = '1' if usebinaries else '0'
    inputparams['extinction_sigma'] = '%.2f' % extinction_sigma
    inputparams['field'] = '%.2f' % field_deg2
    inputparams['icm_lim'] = str(maglim_filtercol)
    inputparams['mag_lim'] = '%.2f' % magnitude_limit
    inputparams['trilegal_version'] = str(trilegal_version)

    # get the coordinates
    inputparams['gc_l'] = '%.3f' % gal_lon
    inputparams['gc_b'] = '%.3f' % gal_lat

    # check if the area is less than 10 deg^2
    if field_deg2 > 10.0:
        LOGERROR("can't have an area > 10 square degrees")
        return None

    # get the extinction parameter. this is by default A[inf] in V. we'll use
    # the value from SF11 generated by the 2MASS DUST service
    extinction_info = dust.extinction_query(gal_lon,
                                            gal_lat,
                                            coordtype='galactic',
                                            forcefetch=forcefetch,
                                            verbose=verbose,
                                            timeout=timeout)
    try:
        Av_infinity = extinction_info['Amag']['CTIO V']['sf11']
        inputparams['extinction_infty'] = '%.5f' % Av_infinity
    except Exception as e:
        LOGEXCEPTION(
            'could not get A_V_SF11 from 2MASS DUST '
            'for Galactic coords: (%.3f, %.3f), '
            'using default value of %s' % (gal_lon, gal_lat,
                                           inputparams['extinction_infty'])
        )


    # get the filter system table
    if filtersystem in TRILEGAL_FILTER_SYSTEMS:
        inputparams['photsys_file'] = (
            TRILEGAL_FILTER_SYSTEMS[filtersystem]['table']
        )
    else:
        LOGERROR('filtersystem name: %s is not in the table of known '
                 'filter systems.\n'
                 'Try the trilegal.list_trilegal_filtersystems() function '
                 'to see all available filter systems.' % filtersystem)
        return None

    # override the complete form param dict now with our params
    trilegal_params = TRILEGAL_DEFAULT_PARAMS.copy()
    trilegal_params.update(inputparams)

    # override the final params with any extraparams
    if extraparams and isinstance(extraparams, dict):
        trilegal_params.update(extraparams)

    # see if the cachedir exists
    if '~' in cachedir:
        cachedir = os.path.expanduser(cachedir)
    if not os.path.exists(cachedir):
        os.makedirs(cachedir)

    # generate the cachefname and look for it
    cachekey = repr(inputparams)
    cachekey = hashlib.sha256(cachekey.encode()).hexdigest()
    cachefname = os.path.join(cachedir, '%s.txt.gz' % cachekey)
    provenance = 'cache'

    lockfile = os.path.join(cachedir, 'LOCK-%s' % cachekey)

    # run the query if results not found in the cache
    if forcefetch or (not os.path.exists(cachefname)):

        # first, check if a query like this is running already
        if os.path.exists(lockfile):
            with open(lockfile,'r') as infd:
                lock_contents = infd.read()
            lock_contents = lock_contents.replace('\n','')

            LOGERROR('this query appears to be active since %s'
                     'in another instance, not running it again' %
                     lock_contents)
            return None

        else:
            with open(lockfile,'w') as outfd:
                outfd.write(datetime.utcnow().isoformat())

        provenance = 'new download'

        try:

            if verbose:
                LOGINFO('submitting TRILEGAL request for input params: %s'
                        % repr(inputparams))

            posturl = TRILEGAL_POSTURL.format(formversion=trilegal_version)

            req = requests.post(posturl,
                                data=trilegal_params,
                                timeout=timeout)
            resp = req.text

            # get the URL of the result file
            resultfile = TRILEGAL_REGEX.search(resp)

            if resultfile:

                resultfile = resultfile[0]
                waitdone = False
                timeelapsed = 0.0

                resultfileurl = '%s/%s' % (
                    TRILEGAL_BASEURL,
                    resultfile.replace('a href=..','')
                )

                if verbose:
                    LOGINFO(
                        'request submitted sucessfully, waiting for results...'
                    )

                # wait for 2 minutes, then try to download the result file
                while not waitdone:

                    if timeelapsed > maxtimeout:
                        LOGERROR('TRILEGAL timed out after waiting for results,'
                                 ' request was: '
                                 '%s' % repr(inputparams))
                        # remove the lock file
                        if os.path.exists(lockfile):
                            os.remove(lockfile)
                        return None

                    time.sleep(refresh)
                    timeelapsed = timeelapsed + refresh

                    try:

                        resreq = requests.get(resultfileurl)
                        resreq.raise_for_status()

                        if verbose:
                            LOGINFO('TRILEGAL completed, retrieving results...')

                        # stream the response to the output cache file
                        with gzip.open(cachefname,'wb') as outfd:
                            for chunk in resreq.iter_content(chunk_size=8192):
                                outfd.write(chunk)

                        tablefname = cachefname
                        waitdone = True
                        if verbose:
                            LOGINFO('done.')

                    except Exception as e:

                        if verbose:
                            LOGINFO('elapsed time: %.1f, result file: %s '
                                    'not ready yet...'
                                    % (timeelapsed, resultfileurl))
                        continue

            else:

                LOGERROR('no result file URL found in TRILEGAL output, '
                         'this is probably an error with the input. '
                         'HTML of error page follows:\n')
                LOGINFO(resp)
                # remove the lock file
                if os.path.exists(lockfile):
                    os.remove(lockfile)
                return None


        except requests.exceptions.Timeout as e:
            LOGERROR('TRILEGAL submission timed out, '
                     'site is probably down. Request was: '
                     '%s' % repr(inputparams))
            return None

        except Exception as e:
            LOGEXCEPTION('TRILEGAL request failed for '
                         '%s' % repr(inputparams))
            return None

        finally:

            # remove the lock file
            if os.path.exists(lockfile):
                os.remove(lockfile)


    # otherwise, get the file from the cache
    else:

        if verbose:
            LOGINFO('getting cached TRILEGAL model result for '
                    'request: %s' %
                    (repr(inputparams)))

        tablefname = cachefname


    # return a dict pointing to the result file
    # we'll parse this later
    resdict = {'params':inputparams,
               'extraparams':extraparams,
               'provenance':provenance,
               'tablefile':tablefname}

    return resdict



def query_radecl(ra,
                 decl,
                 filtersystem='sloan_2mass',
                 field_deg2=1.0,
                 usebinaries=True,
                 extinction_sigma=0.1,
                 magnitude_limit=26.0,
                 maglim_filtercol=4,
                 trilegal_version=1.6,
                 extraparams=None,
                 forcefetch=False,
                 cachedir='~/.astrobase/trilegal-cache',
                 verbose=True,
                 timeout=60.0,
                 refresh=150.0,
                 maxtimeout=700.0):
    '''
    This runs the TRILEGAL query for decimal equatorial coordinates.

    '''

    # convert the ra/decl to gl, gb
    radecl = SkyCoord(ra=ra*u.degree, dec=decl*u.degree)

    gl = radecl.galactic.l.degree
    gb = radecl.galactic.b.degree

    return query_galcoords(gl,
                           gb,
                           filtersystem=filtersystem,
                           field_deg2=field_deg2,
                           usebinaries=usebinaries,
                           extinction_sigma=extinction_sigma,
                           magnitude_limit=magnitude_limit,
                           maglim_filtercol=maglim_filtercol,
                           trilegal_version=trilegal_version,
                           extraparams=extraparams,
                           forcefetch=forcefetch,
                           cachedir=cachedir,
                           verbose=verbose,
                           timeout=timeout,
                           refresh=refresh,
                           maxtimeout=maxtimeout)



def read_model_table(modelfile):
    '''
    This reads a downloaded TRILEGAL model file.

    '''

    infd = gzip.open(modelfile)
    model = np.genfromtxt(infd,names=True)
    infd.close()

    return model