#!/usr/bin/env python2.7 -W ignore::DeprecationWarning
# -*- coding: utf-8 -*-
import os
import commands
from os.path import join, exists, isdir, dirname, basename, split
import shutil
from multiprocessing import Process
import pandas as pd
import nibabel as nib
import numpy as np
import yaml

from utils import tools
from utils import resources as rsc

def create_stir_hs_from_detparams(params_file,output_file, create_projdata_bin, output_format="SimSET"):

    with open(params_file, 'rb') as f:
        params = yaml.load(f.read(), Loader=yaml.FullLoader)
        
    num_rings = params.get("num_rings")
    max_segment = params.get("max_segment")
    max_z = params.get("max_z")
    min_z = params.get("min_z")
    z_crystal_size = params.get("z_crystal_size")
    gap_size = (max_z-min_z-z_crystal_size*num_rings)/(num_rings-1)
    ring_spacing = z_crystal_size + gap_size

    max_td = params.get("max_td")
    min_td = params.get("min_td")
    td_bins = params.get("num_td_bins")
    bin_size = (max_td-min_td)/float(td_bins)
    matrix_size, ring_difference = generate_segments_lists_stir(num_rings, max_segment)

    if output_format=="SimSET":
        views_coordinate = 2
        axial_coordinate = 3
    else:
        views_coordinate = 3
        axial_coordinate = 2

    new_file = open(output_file, "w")
    new_file.write(
        "!INTERFILE  :=\n" + 
        "!imaging modality := PT\n" +
        "name of data file := " + output_file[0:-2] + "s" + "\n" +
        "originating system := " + params.get("scanner_name") + "\n" +
        "!version of keys := STIR3.0\n" +
        "!GENERAL DATA :=\n" +
        "!GENERAL IMAGE DATA :=\n" +
        "!type of data := PET\n" +
        "imagedata byte order := LITTLEENDIAN\n" +
        "!PET STUDY (General) :=\n" +
        "!PET data type := Emission\n" +
        "applied corrections := {None}\n" +
        "!number format := float\n" +
        "!number of bytes per pixel := 4\n" +
        "number of dimensions := 4\n" +
        "matrix axis label [4] := segment\n"
        "!matrix size [4] := " + str(2*max_segment+1) + "\n" +
        "matrix axis label [" + str(views_coordinate) +"] := view\n"
        "!matrix size [" + str(views_coordinate) +"] :=" + str(params.get("num_aa_bins")) + "\n" +
        "matrix axis label ["+ str(axial_coordinate) +"] := axial coordinate\n" +
        "!matrix size [" + str(axial_coordinate) + "] := " + matrix_size + "\n" +
        "matrix axis label [1] := tangential coordinate\n" +
        "!matrix size [1] :=" + str(td_bins) + "\n" +
        "minimum ring difference per segment := " + ring_difference + "\n" +
        "maximum ring difference per segment := " + ring_difference + "\n" +
        "Scanner parameters:= \n" +
        "Scanner type := " + params.get("scanner_name") + "\n" +
        "Number of rings := " + str(num_rings) + "\n" +
        "Number of detectors per ring := " + str(params.get("num_aa_bins")*2) + "\n" +
        "Inner ring diameter (cm) := " + str(params.get("radio_scanner")*2) + "\n" +
        "Average depth of interaction (cm) := " + str(params.get("average_doi")) + "\n" +
        "Distance between rings (cm) := " + str(ring_spacing) + "\n" +
        "Default bin size (cm) := " + str(bin_size) + "\n" +
        "View offset (degrees) := 0\n" +
        "Maximum number of non-arc-corrected bins := " + str(td_bins) + "\n" +
        "Default number of arc-corrected bins := " + str(td_bins) + "\n" +
        "Energy_resolution := " + str(params.get("energy_resolution")*5.11) + "\n" +
        "Reference energy (in keV) := 511\n" +
        "Number of blocks per bucket in transaxial direction := 1\n" +
        "Number of blocks per bucket in axial direction := 1\n" +
        "Number of crystals per block in axial direction := 1\n" +
        "Number of crystals per block in transaxial direction := 1\n" +
        "Number of crystals per singles unit in axial direction := 1\n" +
        "Number of crystals per singles unit in transaxial direction := 1\n" +
        "end scanner parameters:=\n" +
        "effective central bin size (cm) := " + str(bin_size) + "\n" +
        "number of time frames := 1\n" +
        "start vertical bed position (mm) := 0\n" +
        "start horizontal bed position (mm) := 0\n" +
        "!END OF INTERFILE :=\n"
        )
        
def generate_segments_lists_stir(nrings, max_segment):

    last_segment_sinograms = nrings-max_segment
    my_matrix_size = " "
    my_matrix_ring_difference = " "
    for i in range(last_segment_sinograms, nrings):
        my_matrix_size = my_matrix_size + str(i) + ","
        my_matrix_ring_difference = my_matrix_ring_difference + str(i-nrings) + ","
    for i in range(nrings, last_segment_sinograms-1,-1):
        my_matrix_size = my_matrix_size + str(i) + ","
        my_matrix_ring_difference = my_matrix_ring_difference + str(nrings-i) + ","

    my_matrix_size = "{" + my_matrix_size [0:-1] + "}"
    my_matrix_ring_difference = "{" + my_matrix_ring_difference [0:-1] + "}"

    return my_matrix_size, my_matrix_ring_difference