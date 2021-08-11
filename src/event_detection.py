#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jul 22 16:45:23 2021

@author: Peidong SHI
@email: speedshi@hotmail.com
"""


import os
import h5py
import datetime
import numpy as np
from ioformatting import vector2trace
import copy


def eqtprob_eventdetect(dir_probinput, dir_output, sttd_max, twlex, d_thrd, nsta_thrd=3, spttdf_ssmax=None):
    """
    This function is used to detect potential events using the probabilities 
    generated by EQ-transformer. The detection probability, P-phase probability
    S-phase probability of the detected event segments are output to MSEED format
    in the output directory.
    
    Parameters
    ----------
    dir_probinput : str
        path to the EQT probability data set of different stations.
    dir_output : str
        path for data outputs.
    sttd_max : float
        maximum P-P traveltime difference between different stations for 
        the whole imaging area, in second.
    twlex : float
        time in second for extending the time window, roughly equal to the 
        width of P- or S-probability envelope. Value ranges from 0.5-2 second.
    d_thrd : float
        detection threshold. The threshold value depends on the performance of 
        the machine learning model. Use a low threshold to detect more weak events,
        but could also increase false positives. Use a high threshold to detect
        events with more confidance, but could miss some weak or usual events.
        Since we will perform migration on phase probabilities to image and 
        locate the souces, we are using spatial coherency accross the whole array.
        So it is suggestted to use a relatively low threshold for detection, 
        and migration process can later take care of event location and 
        potentially remove false positives by additional event selection process
        later. For EQT, suggestted threshold values from 0.05 - 0.5
    nsta_thrd : int, optional
        minimal number of stations triggered during a specified time period, 
        If there are more triggered stations than this threshold, the algrithem
        determines there is an event in the current searched time period, then
        it will start to ouput probapility data of different stations to the 
        defined output directory. Each event will have a unique folder name 
        according to the starttime of its data segment.
        The default is 3.
    spttdf_ssmax: float, optional
        the maximal P to S arrivaltime difference for a perticular station in 
        second for the imaging area. No need to be very accurate.

    Returns
    -------
    Obspy trace data outputted in MSEED format in the defined output directory.

    """

    if spttdf_ssmax is None:
        spttdf_ssmax = 0.5*sttd_max


    # internal parameters
    pbfname = 'prediction_probabilities.hdf5'  # the common filename of probability file for each station
    dtformat_EQT = '%Y-%m-%dT%H:%M:%S.%fZ'  # the datetime format using in EQT probability hdf5 outputs
    data_size_EQT = 6000  # the data segment size in date points, by default the EQT output are 1 minutes long, thus 6000 points
    dt_EQT = 0.01  # time sampling rate of data in second, for EQT probability output, by default is 0.01 s
    data_sglength = (data_size_EQT-1)*dt_EQT  # data segment length in second, equals 'endtime - starttime'
    N_tit = 1  # number of iteration for settle the starttime and endtime of data segment; should be 1, 2, 3; set 1 for fast calculation, set 2 or 3 if want to obtain better time constrain
    
    datainfo = {}
    datainfo['dt'] = dt_EQT
    
    
    # load timing info and the detection probability
    # obtain the folder name for the results of each station, each folder contain the probability data of one station
    db = {}  # for storing the whole data set: timestamp info + detection probability
    stanames = []
    dirnames = sorted([fdname for fdname in os.listdir(dir_probinput) if os.path.isdir(os.path.join(dir_probinput, fdname))])
    dsg_sttmin = None  # earliest starttime of data segment
    dsg_sttmax = None  # latest endtime of data segment
    for sfdname in dirnames:
        # loop over each station folder, read data set for each station
        station_name = sfdname.split('_')[0]  # the current station name
        pbfile = os.path.join(dir_probinput, sfdname, pbfname)  # the filename of picking probability for the current station
        
        # load probability data set
        pbdf = h5py.File(pbfile, 'r')
        dsg_name = list(pbdf['probabilities'].keys())  # get the name of each probability data segment 
        dsg_starttime = np.array([datetime.datetime.strptime(idsgnm.split('_')[-1], dtformat_EQT) for idsgnm in dsg_name])  # get the starttime of each probability data segment 
        dsg_endtime = np.array([iitime + datetime.timedelta(seconds=data_sglength) for iitime in dsg_starttime])  # get the endtime of each probability data segment 
    
        # find the minimal starttime and maximum endtime
        if dsg_sttmin:
            dsg_sttmin = min(dsg_sttmin, min(dsg_starttime))
        else:
            dsg_sttmin = min(dsg_starttime)
        if dsg_sttmax:
            dsg_sttmax = max(dsg_sttmax, max(dsg_endtime))
        else:
            dsg_sttmax = max(dsg_endtime)
        
        prob_D = []
        for idsg in dsg_name:
            pbdata = np.zeros((data_size_EQT, 3), dtype=np.float32)  # initialize array for load prob data set
            pbdf['probabilities'][idsg].read_direct(pbdata)  # EQT probability data set, shape: 6000*3
            prob_D.append(pbdata[:,0])  # detection probability
            del pbdata
            
        db[station_name] = [dsg_starttime, dsg_endtime, prob_D, dsg_name]  # starting datetime of each data segement and the corresponding detection probability
        stanames.append(station_name)  # all avaliable station names
            
        del station_name, pbfile, pbdf, dsg_name, dsg_starttime, dsg_endtime, prob_D
        
    
    # scan data from 'dsg_sttmin' to 'dsg_sttmax' to search for all potential events/triggers
    # tt1 : the starttime of searched time range
    # tt2 : the endtime of searched time range
    # tts : the starttime of data extraction
    # ttd : the endtime for data extraction, ttd <= tt2
    # tts_sta : the starttime for a probability data segment above threshold at different stations
    # ttd_sta : the endtime for a probability data segment above threshold at different stations
    tt1 = copy.deepcopy(dsg_sttmin)
    ttd_previous = copy.deepcopy(dsg_sttmin)  # the endtime of data extraction for the previous data output
    while tt1 <= dsg_sttmax:
        # Find if there are enough stations have detection values above the 
        # threshold (triggered) at the searched time range. 
        # If yes, then find a event and output data.
        
        # set the endtime for searched time range
        tt2 = tt1 + datetime.timedelta(seconds=(sttd_max+twlex))  # use 'maximum P2S traveltime difference' + 'extend window length' to set the endtime of searching time range
        # make sure tt2 does not exceed the maximum time
        if tt2 > dsg_sttmax:
            tt2 = copy.deepcopy(dsg_sttmax)
        
        for itit in range(N_tit):
            
            if itit > 0:
                tt1 = copy.deepcopy(tts)
                tt2 = copy.deepcopy(ttd)
            
            # initialize parameters
            tts = None
            ttd = None
            tts_sta = {}
            ttd_sta = {}
            nsta_trig = 0  # number of stations triggered
            
            for sta in stanames:
                # loop over each station
                
                # flag to indicate if the current station has already been triggered or not
                station_triggered = False
                
                # maximum detection probability for the current event in the searched time period
                prob_det_max = 0.0
                
                # find all data segments which contain the whole searched time period
                dindx = np.logical_and((db[sta][0] <= tt1), (db[sta][1] >= tt2))  # the index of data segments that include the whole searched time period
                if dindx.any():
                    for isgindex in np.flatnonzero(dindx):
                        # loop over each fulfilled data segment, find the earliest 'tts' and the latest 'ttd'
                        
                        data_sgindex = copy.deepcopy(isgindex)  # the index of the chosen data segment, is an integer
                        data_starttime = db[sta][0][data_sgindex]  # starttime of the chosen data segment
                        data_times = np.array([data_starttime + datetime.timedelta(seconds=iitp*dt_EQT) for iitp in range(data_size_EQT)])  # timestampe of each data point
                        data_probD = db[sta][2][data_sgindex]  # detection probability of the chosen data segment
                        
                        data_pdindex = np.logical_and((data_times >= tt1), (data_times <= tt2))  # the index of probability data point within the detection time range
                        detecid = (data_probD[data_pdindex] >= d_thrd)  # boolen array to indicate whether there are detections above threshold
                        
                        if detecid.any():
                            # have detetion at the current station and the searched time period
                            
                            # determine if this station has been triggered and update the accumulated number
                            if not station_triggered:
                                nsta_trig = nsta_trig + 1  
                                station_triggered = True
                        
                            idfirst = np.flatnonzero(data_pdindex)[0]  # the index of the first point in the searched time period
                            idlast = np.flatnonzero(data_pdindex)[-1]  # the index of the last point in the searched time period
                            
                            # set tts, and update tt2
                            if (data_probD[idfirst] >= d_thrd) and (idfirst > 0) and (data_probD[idfirst-1] >= d_thrd):
                                # starttime and the data point just before the starttime are both above threshold
                                ddinx = np.flatnonzero(data_probD[0:idfirst] < d_thrd)  
                                if ddinx.size > 0:
                                    # get the last occurance for the prior points with a detection value smaller than threshold
                                    tts_temp = data_times[ddinx[-1] + 1] - datetime.timedelta(seconds=twlex)
                                else:
                                    # all the prior data points exceed detection threshold
                                    tts_temp = data_times[0] - datetime.timedelta(seconds=spttdf_ssmax)  # note move the starttime ahead 
                                    
                                del ddinx
                            elif (data_probD[idfirst] >= d_thrd) and (idfirst == 0):
                                # starttime is above the threshold and also is the first point of this segment
                                tts_temp = data_times[0] - datetime.timedelta(seconds=spttdf_ssmax)  # note move the starttime ahead
                            else:
                                # the starttime tt1 has detetion probability below threshold
                                tts_temp = data_times[idfirst + np.argmax(detecid)] - datetime.timedelta(seconds=twlex)
                            
                            # set tts_sta for the current station
                            dprobD_max = max(data_probD[data_pdindex])  # maximum detection probability for the current time segment and station
                            if (dprobD_max > prob_det_max):
                                tts_sta[sta] = copy.deepcopy(tts_temp)
                            # if sta in tts_sta:
                            #     tts_sta[sta] = min(tts_sta[sta], tts_temp)
                            # else:
                            #     tts_sta[sta] = copy.deepcopy(tts_temp)
                            if tts_sta[sta] < ttd_previous:
                                tts_sta[sta] = copy.deepcopy(ttd_previous)
                            
                            # set tts
                            if tts:
                                tts = min(tts, tts_sta[sta])  # tts = min(tts, tts_temp)
                            else:
                                tts = copy.deepcopy(tts_sta[sta])  # tts = copy.deepcopy(tts_temp)
                            # make sure the 'tts' is not earlier than the endtime of the previous data extraction
                            if tts < ttd_previous:
                                tts = copy.deepcopy(ttd_previous)
                            
                            # set tt2
                            if tts > tt1:
                                tt2 = tts + datetime.timedelta(seconds=(sttd_max+twlex))
                            else:
                                tt2 = tt1 + datetime.timedelta(seconds=(sttd_max+twlex))
                            if tt2 > dsg_sttmax:
                                tt2 = copy.deepcopy(dsg_sttmax)
                            
                            del tts_temp
                            
                            # set ttd, and update tt2
                            if (data_probD[idlast] >= d_thrd) and (idlast < data_size_EQT-1) and (data_probD[idlast+1] >= d_thrd):
                                # endtime and the next point of endtime are both above threshold
                                ddinx = np.argmax(data_probD[idlast+1:] < d_thrd)  # first occurance for the remaining points with a detection value smaller than threshold
                                if ddinx > 0:
                                    # the remaining data points have detection value below threshold
                                    ttd_temp = data_times[idlast + ddinx] + datetime.timedelta(seconds=twlex)
                                else:
                                    # all the remaining data points exceed detection threshold
                                    ttd_temp = data_times[-1] + datetime.timedelta(seconds=spttdf_ssmax)  # note move the endtime after
                                    
                                del ddinx
                            elif (data_probD[idlast] >= d_thrd) and (idlast == data_size_EQT-1):
                                # endtime is above the threshold and also is the last point of this segment
                                ttd_temp = data_times[-1] + datetime.timedelta(seconds=spttdf_ssmax)  # note move the endtime after
                            else:
                                # the next point after endtime is below threshold,
                                # or just before or at the endtime is below threshold. 
                                ttd_temp = data_times[idfirst + np.flatnonzero(detecid)[-1]] + datetime.timedelta(seconds=twlex)
                            
                            # set ttd_sta for the current station
                            if (dprobD_max > prob_det_max):
                                ttd_sta[sta] = copy.deepcopy(ttd_temp)
                                prob_det_max = copy.deepcopy(dprobD_max)
                            # if sta in ttd_sta:
                            #     ttd_sta[sta] = max(ttd_sta[sta], ttd_temp)
                            # else:
                            #     ttd_sta[sta] = copy.deepcopy(ttd_temp)
                            if ttd_sta[sta] > dsg_sttmax:
                                ttd_sta[sta] = copy.deepcopy(dsg_sttmax)
                            
                            # set ttd
                            if ttd:
                                ttd = max(ttd, ttd_sta[sta])  # ttd = max(ttd, ttd_temp)
                            else: 
                                ttd = copy.deepcopy(ttd_sta[sta])  # ttd = copy.deepcopy(ttd_temp)
                            if ttd > dsg_sttmax:
                                ttd = copy.deepcopy(dsg_sttmax)
                            
                            # set tt2
                            tt2 = max(tt2, ttd)
                            if tt2 > dsg_sttmax:
                                tt2 = copy.deepcopy(dsg_sttmax)    
                            
                            del idfirst, idlast, ttd_temp, dprobD_max
                            
                        # clear memory
                        del data_sgindex, data_starttime, data_times, data_probD, data_pdindex, detecid
                    del isgindex
                del dindx, prob_det_max
        
            if (nsta_trig < nsta_thrd):
                break
        
        # write P- and S-phase probability data for the current searched time period
        # if there are more triggered stations than the threshold (3 stations)
        # output data from time range: 'tts' to 'ttd'
        if (nsta_trig >= nsta_thrd):
            # print info
            print('----------------------------------------------------------')
            print('Detect event at time range:', tts, '-', ttd)
            print(nsta_trig, 'stations are triggered.')
            print('Start to output data in this time range.')
            
            # after the previous loop over all stations, the 'tt1', 'tt2', 'tts', 'ttd', 'tts_sta', 'ttd_sta' are now fixed
            dir_output_ev = dir_output + '/' + tts.strftime(dtformat_EQT)  # output directory for the current event/time_range
            
            for sta in stanames:
                # loop over each station, check data, and load P S probability, and output avaliable data set
                
                # set the midpoint time for the current station
                if sta in tts_sta:
                    # set the midpoint time between the starttime and endtime tailored for the current station
                    tt_mid =  tts_sta[sta] + (ttd_sta[sta] - tts_sta[sta])/2 
                else:
                    # no detection for the current station
                    # set the midpoint between the starttime and endtime of data extraction
                    tt_mid =  tts + (ttd - tts)/2  
                
                dindx = np.logical_and((db[sta][0] <= tts), (db[sta][1] >= ttd))  # the index of data segments that include the whole searched time period
                if dindx.any():
                    # have data segments that fulfill the requirements
                    # find the data segment where the searched time period is mostly around the center
                    mdtimesdf = np.array([ttdfc.total_seconds() for ttdfc in db[sta][0][dindx] + datetime.timedelta(seconds=0.5*data_sglength) - tt_mid])  # time difference in second between the midpoint of the fulfilled data segments time range and the searched time period
                    data_sgindex = np.flatnonzero(dindx)[np.argmin(abs(mdtimesdf))]  # the index of the chosen data segment, is an integer
                    data_sgname = db[sta][3][data_sgindex]  # the segment name of the chosen data segment
                    data_starttime = db[sta][0][data_sgindex]  # starttime of the chosen data segment
                    data_times = np.array([data_starttime + datetime.timedelta(seconds=iitp*dt_EQT) for iitp in range(data_size_EQT)])  # timestampe of each data point for the chosen data segment
                    data_pdindex = np.logical_and((data_times >= tts), (data_times <= ttd))  # the index of probability data point within the detection time range
                    odata_time = data_times[data_pdindex]  # the timestampe of outout data
                    
                    # set data info               
                    datainfo['station_name'] = sta
                    datainfo['starttime'] = odata_time[0]  # the starttime of the output data
                    
                    # load data set: Detetion, P and S probability
                    pbfile = os.path.join(dir_probinput, sta+'_outputs', pbfname)  # the filename of picking probability for the current station
                    pbdf = h5py.File(pbfile, 'r')
                    pbdata = np.zeros((data_size_EQT, 3), dtype=np.float32)  # initialize array for load prob data set
                    pbdf['probabilities'][data_sgname].read_direct(pbdata)  # EQT probability data set, shape: 6000*3
                    oprob_D = pbdata[data_pdindex,0]  # detection probability
                    oprob_P = pbdata[data_pdindex,1]  # P-phase picking probability
                    oprob_S = pbdata[data_pdindex,2]  # S-phase picking probability
                                    
                    # output detection probability
                    datainfo['channel_name'] = 'PBD'  # note maximum three characters, the last one must be 'D'
                    vector2trace(datainfo, oprob_D, dir_output_ev)
                    
                    # output P-phase picking probability
                    datainfo['channel_name'] = 'PBP'  # note maximum three characters, the last one must be 'P'
                    vector2trace(datainfo, oprob_P, dir_output_ev)
                    
                    # output S-phase picking probability
                    datainfo['channel_name'] = 'PBS'  # note maximum three characters, the last one must be 'S'
                    vector2trace(datainfo, oprob_S, dir_output_ev)
                    
                    # clear memory
                    del mdtimesdf, data_sgindex, data_sgname, data_starttime, data_times, data_pdindex, odata_time
                    del pbfile, pbdf, pbdata, oprob_D, oprob_P, oprob_S
                
                del dindx
            del tt_mid, dir_output_ev
        
            # updata 'ttd_previous'
            ttd_previous = copy.deepcopy(ttd)
        
        # update the starttime for detection
        if ttd:
            tt1 = ttd + datetime.timedelta(seconds=dt_EQT)
        else:
            tt1 = tt2 + datetime.timedelta(seconds=dt_EQT)

        del tts_sta, ttd_sta, tts, ttd, nsta_trig
        
    return    
        
        
    
