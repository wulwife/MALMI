#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jan 13 09:32:40 2022

Functions related to input and output of seismic data.

@author: shipe
"""


import os
import obspy
import glob
import warnings
from ioformatting import read_seismic_fromfd, stream2EQTinput
import gc


def format_AIO(dir_seismic, seismic_channels, dir_output):
    """
    Format seismic data stored simply in one folder so that the ouput data
    can be feed to various ML models.
    Seismic data sets are loaded and formated together for all station.
    Suitable for formatting small data set.

    Parameters
    ----------
    dir_seismic : str
        path to the directory where seismic data are stored all in this folder.
    seismic_channels : list of str
        the used channels of the input seismic data.
        such as ["*HE", "*HN", "*HZ", "*H1", "*H2"].  
    dir_output : str
        directory for outputting seismic data, 
        NOTE do not add '/' at the last.

    Returns
    -------
    None.

    """

    # read in all continuous seismic data in the input folder as an obspy stream
    stream = read_seismic_fromfd(dir_seismic)
    
    # output to the seismic data format that QET can handle 
    stream2EQTinput(stream, dir_output, seismic_channels)
    del stream
    gc.collect()
    
    return


def format_SDS(seisdate, stainv, dir_seismic, seismic_channels, dir_output):
    """
    Format seismic data organized in SDS data structure so that the ouput data
    can be feed to various ML models.
    Seismic data sets are formated per station.
    Suitable for formatting large or long-duration data set.

    Parameters
    ----------
    seisdate : datetime.date
        the date of seismic data to be formated.
    stainv : obspy station inventory object.
        obspy station inventory containing the station information.
    dir_seismic : str
        path to the SDS archive directory.
    seismic_channels : list of str
        the used channels of the input seismic data.
        such as ["*HE", "*HN", "*HZ", "*H1", "*H2"].    
    dir_output : str
        directory for outputting seismic data, 
        NOTE do not add '/' at the last.

    Raises
    ------
    ValueError
        DESCRIPTION.

    Returns
    -------
    None.

    """

    tdate = seisdate  # the date to be processed for SDS data files
    tyear = tdate.year  # year
    tday = tdate.timetuple().tm_yday  # day of the year

    for network in stainv:
        for station in network:
            # loop over each station for formatting input date set
            # and outputting correct input formats for adopted ML models   
            datapath1 = os.path.join(dir_seismic, str(tyear), network.code, station.code)  # station level
            if os.path.exists(datapath1):
                stream = obspy.Stream()  # initilize an empty obspy stream
                for icha in seismic_channels:
                    # loop over each channel to load data of the current station
                    datapath2 = glob.glob(os.path.join(datapath1, '*'+icha+'*'))  # component level
                    if len(datapath2)==0:
                        print("No data found for component: {}! Pass!".format(icha))
                    elif len(datapath2)==1:
                        datapath3 = os.path.join(datapath2[0], '*'+str(tday))  # date level
                        sdatafile = glob.glob(datapath3)  # final seismic data filename for the specified station, component and date
                        if len(sdatafile)==0:
                            print("No data found for date: {} (no {} file)! Pass!".format(seisdate, datapath3))
                        elif len(sdatafile)==1:
                            stream += obspy.read(sdatafile[0])
                        else:
                            raise ValueError("More than one file exist: {} for date: {}!".format(sdatafile, seisdate))
                    else:
                        raise ValueError("More than one path exist: {} for the component: {}!".format(datapath2, icha))
                
                # ouput data for the current station
                if stream.count() > 0:
                    stream2EQTinput(stream, dir_output, seismic_channels)
                else:
                    warnings.warn('No data found at station {} for the specified components: {} or date: {}!'
                                  .format(station.code, seismic_channels, seisdate))
                del stream
            else:
                warnings.warn('No data found for: {}! Pass!'.format(datapath1))
    
    return



