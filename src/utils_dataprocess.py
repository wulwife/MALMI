#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul 13 14:26:55 2021

@author: shipe
"""


import numpy as np


def stream_resampling(stream, sampling_rate=100.0):
    """
    To resample the input seismic data.
    Parameters
    ----------
    stream : obspy stream
        input seismic data.
    sampling_rate : float
        required sampling rate in Hz, default is 100 Hz.

    Returns
    -------
    stream : obspy stream
        output seismic data after resampling.
    
    """
    
    for tr in stream:
        if tr.stats.sampling_rate != sampling_rate:
            if (len(tr.data) > 10):
                # perform resampling
                try:
                    if tr.stats.sampling_rate > sampling_rate:
                        # need lowpass filter before resampling
                        tr.filter('lowpass',freq=0.5*sampling_rate,zerophase=True)
                    tr.resample(sampling_rate=sampling_rate)    
                except:
                    try:
                        tr.interpolate(sampling_rate, method="linear")
                    except:
                        stream.remove(tr)
            else:
                # remove the trave if it only contains too few data points
                stream.remove(tr)
    
    return stream


def maxP2Stt(db_path, hdr_filename, model, precision):
    """
    This function is used to find the maximum traveltime difference between 
    P-phase and S-phase in the imaging area.

    Parameters
    ----------
    db_path : str
        path to travetime data set.
    hdr_filename : str
        header filename of the travetime data set.
    model : str
        traveltime data set filename tage, traveltime data are generated by 
        NonLinLoc software, so the same naming rules applied.
    precision : str
        persicion for traveltime data set, can be 'single' or 'double'.

    Returns
    -------
    tt_psmax : float
        the maximal arrivaltime difference bewteen S-phase and P-phase among 
        all stations in second for all imaging points.
        tt_psmax = max_{all imaging points}(max_{all station}(S_arrt) - min_{all stations}(P_arrt))
    tt_ppmax: fload
        the maximal arrivaltime difference bewteen P-phase among all stations 
        in second for all imaging points.
        tt_ppmax = max_{all imaging points}(max_{all station}(P_arrt) - min_{all stations}(P_arrt)) 
    tt_psmax_ss: float
        the maximal arrivaltime difference between S-phase and P-phase for 
        a perticular station in second for all imaging points.
        tt_psmax_ss = max_{all imaging points, all stations}(S_arrt - P_arrt)
    
    """
    
    from loki import traveltimes
    
    # load traveltime data set-------------------------------------------------
    tobj = traveltimes.Traveltimes(db_path, hdr_filename)
    tp = tobj.load_traveltimes('P', model, precision)  # P-wave traveltime table
    ts = tobj.load_traveltimes('S', model, precision)  # S-wave traveltime table
    
    stations = list(tobj.db_stations)  # station name list
    nstation = len(stations)  # total number of stations
    nxyz= np.size(tp[stations[0]])  # total number of imaging points
    tp_mod=np.zeros([nxyz, nstation])
    ts_mod=np.zeros([nxyz, nstation])
    for i, sta in enumerate(stations):
        tp_mod[:,i]=tp[sta]
        ts_mod[:,i]=ts[sta]
    
    del tp, ts
    
    tt_psmax_ss = np.amax(ts_mod - tp_mod, axis=None)
    
    tp_redmin = np.amin(tp_mod, axis=1)  # minimal P-wave traveltimes over different stations at each imaging point
    tp_redmax = np.amax(tp_mod, axis=1)  # maximal P-wave traveltimes over different stations at each imaging point
    ts_redmax = np.amax(ts_mod, axis=1)  # maximal S-wave traveltimes over different stations at each imaging point 
    
    del tp_mod, ts_mod
    
    tt_psmax = np.amax(ts_redmax - tp_redmin)  # maximal P to S arrivaltime difference over different stations in second among all imaging points
    tt_ppmax = np.amax(tp_redmax - tp_redmin)  # maximal P to P arrivaltime difference over different stations in second among all imaging points
    
    return tt_psmax, tt_ppmax, tt_psmax_ss


def dnormlz(data,n1=0,n2=1,axis=0):
    """
    This function is used to linearly normalize the data to the specified range.
    
    Parameters
    ----------
        data : data to be normalized;
        n1, n2 : the specified range;
        axis : on which axis of the data to perform normalization, None for flatten array;
    
    Returns
    -------
        data : normalized data, dimension is the same as input data.
    """
    
    dmax=np.max(data,axis=axis,keepdims=True)
    dmin=np.min(data,axis=axis,keepdims=True)
    
    k=(n2-n1)/(dmax-dmin)
    b=(dmax*n1-dmin*n2)/(dmax-dmin)
    
    data=k*data+b
    
    return data


def chamferdist(datax, datay):
    """
    To calucate the chamfer distance between the input data cloud x (datax)
    and data cloud y (datay).

    Parameters
    ----------
    datax : numpy array of float
        The input data cloud x.
        shape: number of points x number of dimensions.
    datay : numpy array of float
        The input data cloud y.
        shape: number of points x number of dimensions.

    Returns
    -------
    CD : float
        the calculated chamfer distance between datax and datay.

    """
    
    Nx = datax.shape[0]  # total number of data points in data cloud x
    Ny = datay.shape[0]  # total number of data points in data cloud y
    
    CDx = 0.0
    for ix in range(Nx):
        CDx += min(np.sum((datay - datax[ix,:])**2, axis=1))
    CDx = CDx / Nx

    CDy = 0.0
    for iy in range(Ny):
        CDy += min(np.sum((datax - datay[iy,:])**2, axis=1))
    CDy = CDy / Ny
    
    CD = CDx + CDy
    return CD


def stream_split_gaps(stream, mask_value=0, minimal_continous_points=100):
    """
    Split the stream into unmasked traces.
    Data of certain value will be recognized as gap, will be masked.
    Note this will modefy the input stream in place.

    Parameters
    ----------
    stream : obspy stream object
        input continuous data.
    mask_value : float or None, optional, default is 0.
        the data with this value will be recoginzed as gap. 
    minimal_continous_points : int, optional, default is 100.
        this specifies that at least certain continuous points having the mask_value
        will be recognized as gap.

    Returns
    -------
    obspy stream object
        splited stream.

    """
    
    for tr in stream:
        NPTS = len(tr.data)
        mask = np.full((NPTS,), fill_value=False)
        
        mkindx = np.where(tr.data == mask_value)[0]  
        ii = 0
        NN = len(mkindx)
        while ii < NN-1:
            for jj in range(ii+1, NN):
                if (mkindx[jj] - mkindx[jj-1]) > 1:
                    if (mkindx[jj-1]+1-mkindx[ii]) >= minimal_continous_points:
                        mask[mkindx[ii]:mkindx[jj-1]+1] = True
                    ii = jj
                    break
                elif (jj == NN-1):
                    if (mkindx[jj]+1-mkindx[ii]) >= minimal_continous_points:
                        mask[mkindx[ii]:mkindx[jj]+1] = True
                    ii = jj
                    break
                else:
                    pass
            
        tr.data = np.ma.array(tr.data, mask=mask)
    
    return stream.split()


def merge_dict(dict1, dict2):
    """
    Merge two dictionary.
    Each item (key) in the input dictionary is a 1D numpy array or a list.
    
    If the two dictionary have different keys, the dict without keys will be filled
    with None.

    The input order of dictionary makes sense.

    Parameters
    ----------
    dict1 : dict
        input dictionary 1.
    dict2 : dict
        input dictionary 2.

    Returns
    -------
    dict_m: dict
        merged dictionary.

    """
    
    if (dict1 == {}) and (dict2):
        dict_m = dict2
    elif (dict1) and (dict2 == {}):
        dict_m = dict1
    elif (dict1 == {}) and (dict2 =={}):
        dict_m = {}
    else:
        dict_m = {}
        
        # get the keys for the dictionary
        key1 = list(dict1.keys())
        key2 = list(dict2.keys())
        keys = list(set(key1 + key2))
        
        Nev1 = len(dict1[key1[0]])
        Nev2 = len(dict2[key2[0]])
        
        for ikey in keys:
            if (ikey in key1) and (ikey in key2):
                dict_m[ikey] = np.concatenate((dict1[ikey], dict2[ikey]), axis=0)  # note the order here
            elif (ikey in key1):
                temp = np.full((Nev2), fill_value=None)
                dict_m[ikey] = np.concatenate((dict1[ikey], temp), axis=0)
            elif (ikey in key2):
                temp = np.full((Nev1), fill_value=None)
                dict_m[ikey] = np.concatenate((temp, dict2[ikey]), axis=0)
            else:
                raise ValueError('Unrecognized keys: {}.'.format(ikey))

    return dict_m


def get_picknumber(picks):
    # get the total number of stations and phases associated with picks
    
    key_stations = list(picks.keys())  # station names
    num_station_all = len(key_stations)  # total number of stations having picks
    num_station_PS = 0  # total number of stations having both P and S picks
    num_station_P = 0  # total number of stations having only P pick
    num_station_S = 0  # total number of stations having only S pick
    num_P_all = 0  # total number of P picks
    num_S_all = 0  # total number of S picks
    for ista in key_stations:
        if ('P' in picks[ista]) and ('S' in picks[ista]):
            # have both P and S picks
            num_station_PS += 1  
            num_P_all += 1
            num_S_all += 1
        elif ('P' in picks[ista]):
            # have only P pick
            num_station_P += 1
            num_P_all += 1
        elif ('S' in picks[ista]):
            # have only S pick
            num_station_S += 1
            num_S_all += 1
        else:
            raise ValueError('Case not expected: {}!'.format(picks[ista]))
    
    assert(num_station_all == num_station_PS + num_station_P + num_station_S)
    assert(num_P_all == num_station_PS + num_station_P)
    assert(num_S_all == num_station_PS + num_station_S)
    
    return num_station_all, num_station_PS, num_station_P, num_station_S, num_P_all, num_S_all


def pickarrvt_rmsd(pick, arrvt):
    # calculate the root-mean-square deviation between picks and theoretical arrivaltimes in second
    # not all stations and phases have picks, but all have theoretical arrivaltimes
    
    if pick:  # not empty
        rmsd = 0.0  # root-mean-square deviation
        npicks = 0  # total number of picks
        pick_stations = list(pick.keys())  # picked stations
        for ista in pick_stations:  # loop over each picked station
            if 'P' in pick[ista]:
                rmsd += (pick[ista]['P']-arrvt[ista]['P']) * (pick[ista]['P']-arrvt[ista]['P'])
                npicks += 1
            if 'S' in pick[ista]:
                rmsd += (pick[ista]['S']-arrvt[ista]['S']) * (pick[ista]['S']-arrvt[ista]['S'])
                npicks += 1
        rmsd = np.sqrt(rmsd/npicks)
    else:
        rmsd = None
    return rmsd


def pickarrvt_mae(pick, arrvt):
    # calculate the mean absolute error between picks and theoretical arrivaltimes in second
    # not all stations and phases have picks, but all have theoretical arrivaltimes
    
    if pick:  # not empty
        mae = 0.0  # mean absolute error
        npicks = 0  # total number of picks
        pick_stations = list(pick.keys())  # picked stations
        for ista in pick_stations:  # loop over each picked station
            if 'P' in pick[ista]:
                mae += abs(pick[ista]['P']-arrvt[ista]['P'])
                npicks += 1
            if 'S' in pick[ista]:
                mae += abs(pick[ista]['S']-arrvt[ista]['S'])
                npicks += 1
        mae = mae/npicks
    else:
        mae = None
    return mae



