from os.path import join,dirname,abspath,isdir,basename,exists
import os, sys
import shutil
import datetime, time
from multiprocessing import Process
from utils import resources as rsc
from utils import tools
import yaml
import numpy as np
import simset_tools
import subprocess

class SimSET_Simulation(object):
    """This class provides functions to run a SimSET simulation."""

    def __init__(self,params,config,act_map,att_map,scanner,projections_dir):

        #Initialization
        self.simpet_dir = dirname(abspath(__file__))

        self.params = params
        self.config = config
        self.scanner = scanner

        self.simset_dir = self.config.get("dir_simset")

        self.act_map = act_map
        self.att_map = att_map
        self.output_dir = projections_dir
        self.center_slice = params.get("center_slice")

        self.sim_dose = params.get("total_dose")
        self.s_photons = params.get("sampling_photons")
        self.photons = params.get("photons")
        self.sim_time = params.get("simulation_time")
        self.divisions = params.get("divisions")

        self.detlistmode = params.get("detlistmode")
        self.phglistmode = params.get("phglistmode")
        self.add_randoms = params.get("add_randoms")

    def run(self):

        processes = []

        for division in range(self.divisions):

            division_dir = join(self.output_dir, "division_" + str(division))
            os.makedirs(division_dir)
            p = Process(target=self.run_simset_simulation, args=(division_dir,))
            processes.append(p)
            p.start()
            time.sleep(5)

        print(" ")

        for process in processes:
            process.join()

        print(" ")

        self.simulation_postprocessing()

    def run_simset_simulation(self,sim_dir):

        log_file = join(sim_dir, "logging.log")

        print("Starting simulation for %s" % os.path.basename(sim_dir))

        act, act_data = tools.nib_load(self.act_map)

        # It generates a new act_table for the simulation
        if self.sim_dose !=0:
            phantom_counts = np.sum(act_data)
            voxel_size = act.affine[0,0]*act.affine[1,1]*act.affine[2,2]/1000
            phantom_dose = abs(phantom_counts*voxel_size) #uCi
            act_table_factor = self.sim_dose*1000/phantom_dose
        else:
            act_table_factor = 1

        # Creates the data files from the simulation maps
        act_img = self.act_map[0:-3] + "img"
        att_img = self.att_map[0:-3] + "img"
        shutil.copy(act_img,join(sim_dir,"act.dat"))
        shutil.copy(att_img,join(sim_dir,"att.dat"))

        # If Sampling Photons is 0, importance sampling is deactivated, so we use photons as the input.
        if self.add_randoms ==1:
            sim_photons = 0
            print("WARNING: add_randoms=0, so simulation is forced to realistic noise")
            print("Importance sampling is also being deactivated")
            print("All these means the simulation can take very long...")

        elif self.s_photons == 0 and self.photons !=0:
            sim_photons = self.photons/self.divisions

        else:
            sim_photons = self.s_photons

        sim_time = float(self.sim_time)/self.divisions

        my_phg = self.prepare_simset_files(sim_dir, act_table_factor, act, sim_photons, sim_time, 0)
        my_log = join(sim_dir,"simset_s0.log")

        command = "%s/bin/phg %s > %s" % (self.simset_dir, my_phg, my_log)
        tools.osrun(command, log_file)

        rec_weight = join(sim_dir,"rec.weight")
        det_hf = join(sim_dir, 'det_hf.hist')
        phg_hf = join(sim_dir, 'phg_hf.hist')

        if self.s_photons != 0 and self.params.get("add_randoms") != 1:
            if self.photons!=0:
                sim_photons = self.photons/self.divisions
            else:
                sim_photons = self.photons

            # Removes counts for preparing for the next simulation
            os.remove(rec_weight)
            if exists(det_hf):
                os.remove(det_hf)
            if exists(phg_hf):
                os.remove(phg_hf)

            my_phg = self.prepare_simset_files(sim_dir, act_table_factor, act, sim_photons, sim_time, 1)
            my_log = join(sim_dir,"simset_s1.log")

            print("Running the sencond simulation with importance sampling...")
            print("\n")

            command = "%s/bin/phg %s > %s" % (self.simset_dir, my_phg, my_log)
            tools.osrun(command, log_file)

        if self.add_randoms == 1:

            coincidence_window = self.scanner.get("coincidence_window")

            simset_tools.add_randoms(sim_dir, self.simset_dir, coincidence_window, rebin=True, log_file=log_file)

        simset_tools.process_weights(rec_weight,sim_dir,self.scanner,self.add_randoms)

        print("Finished simulation for %s" % os.path.basename(sim_dir))

    def prepare_simset_files(self, sim_dir, act_table_factor, act, sim_photons, sim_time, sampling):

        log_file = join(sim_dir, "logging.log")
        # Establishing necessary parameters
        scanner_radius = self.scanner.get("scanner_radius")
        scanner_axial_fov = self.scanner.get("axial_fov")

        # We activate det_listmode if demanded by user or if add_randoms is on
        if self.add_randoms==1:
            det_listmode = 1
            add_randoms = True
        elif self.detlistmode==1:
            det_listmode = 1
            add_randoms = False
        else:
            det_listmode = 0
            add_randoms = False

        # Creating the act table for the simulation....
        my_act_table = join(sim_dir,"phg_act_table")
        simset_tools.make_simset_act_table(act_table_factor, my_act_table, log_file=log_file)

        # Creating the phg for the simulation...
        my_phg_file = join(sim_dir,"phg.rec")
        simset_tools.make_simset_phg(self.config, my_phg_file, sim_dir, act, scanner_radius, scanner_axial_fov, self.center_slice,
                                     sim_photons, sim_time, add_randoms, self.phglistmode, sampling, log_file=log_file)

        my_det_file = join(sim_dir,"det.rec")
        simset_tools.make_simset_cyl_det(self.scanner, my_det_file, sim_dir, det_listmode, log_file=log_file)

        my_bin_file = join(sim_dir,"bin.rec")
        simset_tools.make_simset_bin(self.config, my_bin_file, sim_dir, self.scanner, add_randoms, log_file=log_file)

        simset_tools.make_index_file(sim_dir, self.simset_dir, log_file=log_file)

        return my_phg_file

    def simulation_postprocessing(self):

        print("Postprocessing simulation...")
        print(" ")
        #All the parallel simulations are combined in division 0

        log_file = join(self.output_dir, "postprocessing.log")

        division_zero = join(self.output_dir, "division_0")

        for image in ["trues", "scatter", "randoms"]:

            zero_image = join(division_zero, image + ".hdr")

            if exists(zero_image):

                print('Adding sinograms for %s' % image)

                for division in range(1,self.divisions):
                    division_dir = join(self.output_dir, "division_" + str(division))
                    division_image = join(division_dir, image + ".hdr")
                    message = 'Adding %s from simulation %s' % (image,division)
                    tools.log_message(log_file, message)
                    tools.operate_images_analyze(zero_image,division_image,zero_image,'sum')

        for hist in ["phg_hf.hist", "det_hf.hist"]:

            zero_hist = join(division_zero, hist)

            if exists(zero_hist):

                print(" ")
                print('Adding History Files for %s' % hist)

                filelist = ''
                output = join(division_zero, "full_" + hist)

                for division in range(self.divisions):
                    division_dir = join(self.output_dir, "division_" + str(division))
                    division_hist = join(division_dir, hist)
                    filelist = filelist + division_hist + ' '

                simset_tools.combine_history_files(self.simset_dir,filelist, output)

                shutil.move(output,zero_hist)

        if self.add_randoms ==1:

            # To have randoms in the final history file, we need to add randoms to the final det_hf.hist
            print('Adding randoms to the the history file...')

            coincidence_window = self.scanner.get("coincidence_window")

            simset_tools.add_randoms(division_zero, self.simset_dir, coincidence_window,
                                     rebin=False, log_file=log_file)

            det_hist = join(division_zero, 'det_hf.hist')
            randoms_hist = join(division_zero, 'randoms.hist')
            output = join(division_zero, 'fulldet_hf.hist')

            simset_tools.combine_history_files(self.simset_dir,filelist, output)

            shutil.move(output,det_hist)
            os.remove(randoms_hist)

        #Once everything is combined in division_0, remove the other divisions
        for division in range(1,self.divisions):
            division_dir = join(self.output_dir, "division_" + str(division))
            shutil.rmtree(division_dir)

class SimSET_Reconstruction(object):
    """This class provides functions to reconstruct a SimSET simulation."""

    def __init__(self,params,config,att_map,scanner,reconstructions_dir,recons_type):

        #Initialization
        self.simpet_dir = dirname(abspath(__file__))
        self.simset_dir = config.get("dir_simset")
        self.dir_stir = config.get("dir_stir")

        self.input_dir = projections_dir
        self.output_dir = join(reconstructions_dir,"recons_type")

        self.params = params
        self.config = config
        self.scanner = scanner

        self.scatt_corr_factor = scanner.get("analytic_scatt_corr_factor")
        self.add_randoms = params.get("add_randoms")
        self.random_corr_factor = scanner.get("analytic_randoms_corr_factor")

        self.do_pre_att_correction = scanner.get('analytical_att_correction')
        self.do_recons_att_correction = scanner.get('stir_recons_att_corr')

        if self.do_pre_att_correction == 1 and self.do_recons_att_correction == 1:
            self.do_pre_att_correction == 0
            raise Warning ('WARNING: both pre and recons att corrections are both active...Ignoring pre-correction')

        self.att_map = att_map
        self.input_dir = projections_dir
        self.output_dir = reconstructions_dir

        self.log_file = join(self.output_dir, "recons.log")

    def run(self):

        if not exists(self.output_dir):
            os.makedirs(self.output_dir)

        prepare_sinograms()

    def prepare_sinograms(self):

        trues_sino = join(self.input_dir, "trues.hdr")
        scatter_sino = join(self.input_dir, "scatter.hdr")
        randoms_sino = join(self.input_dir, "randoms.hdr")
        corr_scatter_sino = join(self.input_dir, "corr_scatter.hdr")
        corr_randoms_sino = join(self.input_dir, "corr_randoms.hdr")
        my_simset_sino = join(self.input_dir, "my_sinogram.hdr")
        additive_sinogram = join(self.input_dir, "additive_sinogram.hdr")

        tools.operate_single_image(scatter_sino, "mult", self.scatt_corr_factor, corr_scatter_sino, self.log_file)
        tools.operate_images_analyze(trues_sino,corr_scatter_sino,my_simset_sino,operation='sum')
        tools.smooth_analyze(corr_scatter_sino,20,corr_scatter_sino)

        if self.add_randoms == 1:

            tools.operate_single_image(randoms_sino, "mult", self.random_corr_factor, corr_randoms_sino, self.log_file)
            tools.operate_images_analyze(my_simset_sino,corr_randoms_sino,my_simset_sino,operation='sum')
            tools.smooth_analyze(corr_randoms_sino,20,corr_randoms_sino)
            tools.operate_images_analyze(corr_scatter_sino,corr_scatter_sino,additive_sinogram,operation='sum')

        else:

            tools.copy_analyze(corr_scatter_sino,additive_sinogram)

        if self.scanner.get('analytical_att_correction') == 1:

            phg_file = join(self.input_dir,"phg.rec")
            output = join(self.input_dir, "attenuation.hdr")
            simset_tools.simset_calcattenuation(self.simset_dir,phg_file,output,trues_sino,nrays=1)
