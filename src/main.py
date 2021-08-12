#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Aug 11 13:41:56 2021

@author: Peidong Shi
@email: speedshi@hotmail.com

MALMI main function - building a whole framework.
"""


from ioformatting import stream2EQTinput, stainv2json


class MALMI:

    def __init__(self, dir_seismic, dir_output, n_processor=1):
        """
        Initilize global input and output paramaters, configure MALMI.
        Parameters
        ----------
        dir_seismic : str
            path to raw continuous seismic data.
        dir_output : str
            path for outputs.
        n_processor : int, default: 1
            number of CPU processors for parallel processing.
        Returns
        -------
        None.

        """
        self.dir_seismic = dir_seismic
        
        # get the foldername of the input seismic data, used as the identifer of the input data set
        if self.dir_seismic[-1] == '/':
            fd_seismic = self.dir_seismic.split('/')[-2]
        else:
            fd_seismic = self.dir_seismic.split('/')[-1]
            
        self.dir_ML = dir_output + "/data_QET/" + fd_seismic  # directory for ML outputs
        self.dir_prob = self.dir_ML + '/prob_and_detection'  # output directory for ML probabilities
        self.dir_migration = dir_output + '/data_loki/' + fd_seismic  # directory for migration outputs
        self.n_processor = n_processor  # number of threads for parallel processing

        self.dir_mseed = self.dir_ML + "/mseeds"  # directory for outputting seismic data for EQT, NOTE do not add '/' at the last part
        self.dir_EQTjson = self.dir_ML + "/json"  # directory for outputting station json file for EQT
        self.dir_lokiprob = self.dir_migration + '/prob_evstream'  # path for probability outputs of different events


    def format_ML_inputs(self, file_station, channels=["*HE", "*HN", "*HZ"]):
        """
        Format input data set for ML models.
        Parameters
        ----------
        file_station : str
            station metadata file, in FDSNWS station text format: *.txt or StationXML format: *.xml.
        channels : list of str, default: ["*HE", "*HN", "*HZ"]
            channels of the input seismic data.

        Returns
        -------
        None.

        """
        
        import obspy
        import os
        
        print('MALMI starts to format input data set for ML models:')
        
        # read in continuous seismic data as obspy stream and output to the data format that QET can handle 
        file_seismicin = sorted([fname for fname in os.listdir(self.dir_seismic) if os.path.isfile(os.path.join(self.dir_seismic, fname))])
        stream = obspy.Stream()
        for dfile in file_seismicin:
            stream += obspy.read(os.path.join(self.dir_seismic, dfile))
        
        stream2EQTinput(stream, self.dir_mseed, channels)
        
        # create station jason file for EQT------------------------------------
        stainv2json(file_station, self.dir_mseed, self.dir_EQTjson)
        print('MALMI_format_ML_inputs complete!')

    
    def generate_prob(self, input_MLmodel, overlap=0.5):
        """
        Generate event and phase probabilities using ML models.
        Parameters
        ----------
        input_MLmodel : str
            path to a trained EQT model.
        overlap : float, default: 0.5
            overlap rate of time window for generating probabilities. e.g. 0.6 means 60% of time window are overlapped.

        Returns
        -------
        None.

        """
        
        from EQTransformer.utils.hdf5_maker import preprocessor
        from EQTransformer.utils.plot import plot_data_chart
        from EQTransformer.core.predictor import predictor
        
        print('MALMI starts to generate event and phase probabilities using ML models:')
        # create hdf5 data for EQT inputs--------------------------------------
        stations_json = self.dir_EQTjson + "/station_list.json"  # station JSON file
        preproc_dir = self.dir_ML + "/preproc_overlap{}".format(overlap)  # path of the directory where will be located the summary files generated by preprocessor step
        # generate hdf5 files
        preprocessor(preproc_dir=preproc_dir, mseed_dir=self.dir_mseed, 
                     stations_json=stations_json, overlap=overlap, 
                     n_processor=1)
        
        # show data availablity for each station-------------------------------
        file_pkl = preproc_dir + '/time_tracks.pkl'
        time_interval = 1  # Time interval in hours for tick spaces in xaxes
        plot_data_chart(time_tracks=file_pkl, time_interval=time_interval, dir_output=preproc_dir)
        
        # generate event and phase probabilities-------------------------------
        dir_hdf5 = self.dir_mseed + '_processed_hdfs'  # path to the hdf5 and csv files
        predictor(input_dir=dir_hdf5, input_model=input_MLmodel, output_dir=self.dir_prob,
                  output_probabilities=True, estimate_uncertainty=False,
                  detection_threshold=0.1, P_threshold=0.1, S_threshold=0.1, 
                  keepPS=False, number_of_cpus=self.n_processor,
                  number_of_plots=100, plot_mode='time_frequency')
        print('MALMI_generate_prob complete!')

            
    def event_detect_ouput(self, sttd_max, spttdf_ssmax, twlex=2, d_thrd=0.1, nsta_thrd=3):
        """
        event detection based on the ML predicted event probabilites
        and output the corresponding phase probabilites of the detected events.
        Parameters
        ----------
        sttd_max : float
            maximum P-P traveltime difference between different stations for 
            the whole imaging area, in second.
        spttdf_ssmax : float
            the maximal P to S arrivaltime difference for a perticular station 
            in second for the whole imaging area, no need to be very accurate.
        twlex : float, optional
            time in second for extend the time window, roughly equal to 
            the width of P- or S-probability envelope. The default is 2.
        d_thrd : float, optional
            detection threshold for detect events from the ML predicted event 
            probabilities. The default is 0.1.
        nsta_thrd : int, optional
            minimal number of stations triggered during a specified time period.
            The default is 3.

        Returns
        -------
        None.

        """
        
        from event_detection import eqtprob_eventdetect
        
        print('MALMI starts to detect events based on the ML predicted event probabilites and output the corresponding phase probabilites of the detected events:')
        eqtprob_eventdetect(self.dir_prob, self.dir_lokiprob, sttd_max, twlex, d_thrd, nsta_thrd, spttdf_ssmax)
        print('MALMI_event_detect_ouput complete!')


    def migration(self, dir_tt, tt_ftage='layer', probthrd=0.001):
        """
        Perform migration based on input phase probabilites

        Parameters
        ----------
        dir_tt : str
            path to travetime data set.
        tt_ftage : str, optional
            traveltime data set filename tage. The default is 'layer'.
        probthrd : float, optional
            probability normalization threshold. If maximum value of the input 
            phase probabilites is larger than this threshold, the input trace 
            will be normalized (to 1). The default is 0.001.

        Returns
        -------
        None.

        """
        
        from loki.loki import Loki
        
        print('MALMI start to perform migration:')
        dir_lokiout = self.dir_migration + '/result_MLprob'  # path for loki outputs
        tt_hdr_filename = 'header.hdr'  # travetime data set header filename
        
        inputs = {}
        inputs['model'] = tt_ftage  # traveltime data set filename tage
        inputs['npr'] = self.n_processor  # number of cores to run
        inputs['normthrd'] = probthrd  # if maximum value of the input phase probabilites is larger than this threshold, the input trace will be normalized (to 1)
        comp = ['P','S']  # when input data are probabilities of P- and S-picks, comp must be ['P', 'S']
        precision = 'single'  # persicion for traveltime data set, 'single' or 'double'
        extension = '*'  # seismic data filename for loading, accept wildcard input, for all data use '*'
        
        l1 = Loki(self.dir_lokiprob, dir_lokiout, dir_tt, tt_hdr_filename, mode='locator')
        l1.location(extension, comp, precision, **inputs)
        print('MALMI_migration complete!')
        
        
