#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jun 24 16:23:38 2021

@author: Peidong SHI
@email: speedshi@hotmail.com
"""


from pandas import to_datetime
import os


def stream2EQTinput(stream, dir_output):
    """
    This function is used to format the input obspy stream into the EQ-Transformer 
    acceptable seismic data inputs.
    
    The three component seismic data of a station should be downloaded at the same time range.
    The output filename contains the time range of the data. For a perticular station,
    the starttime and endtime with a wider range of the three component is used as the 
    unified time range in the output filename.
    So don't split different component data of the same station to differnt stream,
    they must be kept in the same stream and be checked for outputting. You can simply
    merge different streams to a final complete stream which contrain all stations or at
    least all components of the same station, and then pass the steam to this function.

    In general the seismic data (stream) span a day (data are usually downloaded daily). 
    However, this function also accept data time range longer or smaller than a day.
    But using daily data segment is highly recommended, because by default the EQ-Transformer
    are set to process this kind of data (daily date segment). It now also works for longer or 
    short time range. But there is no guarantee that the future updated version will also 
    support this feature.

    Parameters
    ----------
    stream : obspy stream
        input seismic data.
    dir_output : str
        directory for outputting.

    Returns
    -------
    None.

    Example
    -------
    dir_output = '/Users/human/eqt/examples/mseeds'
    stream2EQTinput(stream, dir_output)
    """
    
    
    timeformat = "%Y%m%dT%H%M%SZ"  # NOTE here output until second
    components = ["E", "N", "Z", "1", "2"]
    
    # scan all traces to get the station names
    stations = []
    for tr in stream:
        sname = tr.stats.station
        if sname not in stations:
            stations.append(sname)
    del tr
    
    # for a particular station, first check starttime and endtime, then output data
    for ista in stations:
        
        # scan different components for getting a unified time range (choose the wider one) for a perticular station
        dcount = 0
        for icomp in components:
            stdata = stream.select(station=ista, component=icomp)
            if stdata.count() > 0:
                for tr in stdata:
                    if dcount == 0:
                        starttime = tr.stats.starttime
                        endtime = tr.stats.endtime
                    else:
                        starttime = min(starttime, tr.stats.starttime)
                        endtime = max(endtime, tr.stats.endtime)
                    dcount += 1
            del stdata
    
        # round datetime to the nearest second, and convert to the setted string format
        starttime_str = to_datetime(starttime.datetime).round('1s').strftime(timeformat)
        endtime_str = to_datetime(endtime.datetime).round('1s').strftime(timeformat)
    
        # output data for each station, the data from the same station are output 
        # to the same folder
        # creat a folder for each station and output data in the folder
        dir_output_sta = os.path.join(dir_output, ista)
        if not os.path.exists(dir_output_sta):
            os.makedirs(dir_output_sta)
        
        # Output data for each station and each component
        # For a particular station, the three component (if there are) share
        # the same time range in the final filename.
        for icomp in components:
            stdata = stream.select(station=ista, component=icomp)
            if stdata.count() > 0:
                OfileName = stdata[0].id + '__' + starttime_str + '__' + endtime_str + '.mseed'
                stdata.write(os.path.join(dir_output_sta, OfileName), format="MSEED")
                    
                    
    return




