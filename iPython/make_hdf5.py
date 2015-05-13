#!/usr/bin/env python

"""

Make a HDF5 binary from lots of CSV files so it can be easily used in pandas

"""

import sys
import argparse
import pandas as pd
import numpy as np
import glob
import math
from itertools import product, chain, permutations
from shutil import copyfile


def load_df(folders, filestem):
    """Load dataframes with CSV files from several folders in directory arg,
    from CSV files named filestem*.dat

    Works by first making a large CSV file from all the consituent CSV files,
    and then reading that into a dataframe.

    I did try using the concat() and merge() methods, however their performance
    is much worse - appending is numpy's slow point, and it consumed a lot
    of memory to keep all those individual dataframes open and then concat them.
    """
    for fo in folders:
        print fo
        file_list = [fi for fi in glob.glob(fo + "/%s*.dat" % filestem)]

    if not file_list:
        raise IndexError("file_list is empty - are you sure you've input the correct folders?")

    # Make a copy of the first file (so we can keep the column headers)
    copyfile(file_list[0], "merge.csv")

    # Now add the data rows of the rest of the files to the massive csv file
    with open("merge.csv", "a") as fout:
        for csv in file_list[1:]:
            with open(csv, "r") as fin:
                next(fin)  # skip header
                for line in fin:
                    fout.write(line)

    df = pd.read_csv("merge.csv", delimiter=",")

    # rename from column "lambda" to "lambda_"
    df.rename(columns={'lambda':'lambda_'}, inplace=True)

    # Fix the constraints column, such that the ones that pass (i.e. == "",
    # which pandas interprets as NaN) have NaN replaced by something sensible
    df.fillna({"constraints":""}, axis=0, inplace=True)

    print len(df.index)
    print df.columns.values
    return df


def store_xsec(df):
    """
    Calculate total cross-section & scaled cross-sections
    for gg->h1->a1a1, gg->h2->a1a1, gg->h2->h1h1,
    with final states 4tau, 2b2tau, 4b.
    Denoted as gg -> X -> YY ->f1f1f2f2
    """
    process_scaled = [] # Store them for later
    process = []

    # (no constraint on if ggh is hSM)
    X = ["h1", "h2"]
    Y = ["a1", "h1"]
    F = ["tautau", "bb"]

    for x,y in product(X,Y):
        if x == y:
            continue
        for f1, f2 in product(F,F):
            ff = ""
            factor = 1
            if f1 == f2 == "tautau":
                ff = "4tau"
            elif f1 == f2 == "bb":
                ff = "4b"
            else:
                factor = 2
                ff = "2b2tau"
            name = "xsec_scaled_"+x+"_"+"2"+y+"_"+ff
            if not name in process_scaled:
                # store scaled total XS * BR
                process_scaled.append(name)
                df[name] = df[x+"ggrc2"] * df["Br"+x+y+y] * df["Br"+y+f1] * df["Br"+y+f2] * factor
                # store actual XS * BR
                name = name.replace("_scaled", "")
                process.append(name)
                df[name] = df["xsec_ggf13_"+x] * df[x+"ggrc2"] * df["Br"+x+y+y] * df["Br"+y+f1] * df["Br"+y+f2] * factor


def subset_pass_constraints(df):
    """Return dataframe where points pass all constraints, except a few

    Some sneaky itertools use here to get all the possible permutations of
    constraint strings, for varying numbers of constraints.

    I suppose an easier way would be to take the constrainsts string,
    then do a replace() with each constraint and see what's left over.
    """

    # Here we include all the constraints strings to test against.
    constraints = [
        r"Muon magn. mom. more than 2 sigma away",
        r"Relic density too small (Planck)"
    ]

    # Make a list of all possible permutations, with varying numbers of constraints
    # i.e. if we have 3, then this will include:
    #  1, 2, 3, 1+2, 2+1, 1+3, 3+1, 2+3, 3+2, 1+2+3
    # We join with a "/" since this is how multiple constraint strings are stored in the CSV
    # This is why I love python
    all_permutations = chain.from_iterable(permutations(constraints, r) for r in range(1, len(constraints)+1))
    all_permutations_str = ["/".join(list(p)) for p in all_permutations]
    print "Ignoring constraint combos:", all_permutations_str

    # Check the constrainst column against all permutations
    # Want it to match at least one of the constraint strings
    # Note that the result variable is a Series of True/False, one for
    # each param point. So by OR-ing, we check points pass *any* of
    # the constraints we want to ignore. However we AND the del_a_mu constraint
    # because ALL points must satisfy it (otherwise get points that pass
    # all other constriants but have -ve del_a_mu)
    result = (df["constraints"] == "")  # passing all constraints
    result = result & (df['Del_a_mu'] > 0) # Check that delta a_mu is +ve
    for p in all_permutations_str:
        result = result | (df['constraints'] == p)

    return df[result]


def subset_mass(df, min_mass, max_mass, mass_var):
    """Make subset based on range of object mass"""
    mass_max = df[mass_var] < max_mass
    mass_min = df[mass_var] > min_mass
    return df[mass_min & mass_max]


def make_dataframes(folders):
    """Load files into Panda dataframes

    CSV files read in are named output*.dat and output_good*.dat, and are
    pulled from the folders listed in the arg.
    """

    # csv_directory = "/Users/robina/Dropbox/4Tau/NMSSM-Scan/data"
    # csv_directory = "/hdfs/user/ra12451/NMSSM-Scan/"

    df_orig = load_df(folders, "output")
    # df_orig = load_df(csv_directory, folders, "output_good")

    # Load up the glu-glu cross sections for 13 TeV
    cs = pd.read_csv("parton_lumi_ratio.csv")
    masses = cs["MH [GeV]"].tolist()
    xsec_ggf13 = cs["ggF 13TeV cross section [pb]"].tolist()

    def find_xsec(mass):
        m = min(range(len(masses)), key=lambda x: abs(masses[x]-mass))
        return xsec_ggf13[m]

    # Store SM cross section for gg fusion at 13 TeV for production of m1 and m2
    df_orig["xsec_ggf13_h1"] = df_orig.apply(lambda row: find_xsec(row['mh1']), axis=1)
    df_orig["xsec_ggf13_h2"] = df_orig.apply(lambda row: find_xsec(row['mh2']), axis=1)

    store_xsec(df_orig)

    # Make some subsets here:
    # Points passing all experimental constraints
    df_pass_all = subset_pass_constraints(df_orig)

    # subset with 2m_tau < ma1 < 10
    df_ma1Lt10 = subset_mass(df_pass_all, 3.554, 10, "ma1")

    mhmin, mhmax = 122.1, 128.1
    # subset with h1 as h_125
    df_h1SM = subset_mass(df_pass_all, mhmin, mhmax, "mh1")

    # subset with h2 as h_125
    df_h2SM = subset_mass(df_pass_all, mhmin, mhmax, "mh2")

    n_orig = len(df_orig.index)
    n_pass_all = len(df_pass_all.index)

    def percent_str(numerator, denominator):
        return "%.3f %% +- %.3f %%" % (100*numerator/float(denominator), 100*math.sqrt(numerator)/float(denominator))

    print "Running over", n_orig, "points"
    print n_pass_all, "points passing all constraints (= %s)" % percent_str(n_pass_all, n_orig)
    print len(df_ma1Lt10.index), "of these have 2m_tau < ma1 < 10 GeV (= %s)" % percent_str(len(df_ma1Lt10.index), n_pass_all)
    print len(df_h1SM.index), "points in the h1 = h(125) subset (= %s)" % percent_str(len(df_h1SM.index), n_pass_all)
    print len(df_h2SM.index), "points in the h2 = h(125) subset (= %s)" % percent_str(len(df_h2SM.index), n_pass_all)
    print ""

    return df_orig, df_pass_all, df_ma1Lt10, df_h1SM, df_h2SM


#---------------------------------------------
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="output HDF5 filename")
    parser.add_argument("input", nargs="*", help="folders with CSV files")
    args = parser.parse_args()

    if not args.input:
        print "You need to specify an input directory"
        sys.exit(1)

    job_folders = [
        "/Users/robina/Dropbox/4Tau/NMSSM-Scan/data/jobs_50_MICRO_28_Apr_15_1404",
        "/Users/robina/Dropbox/4Tau/NMSSM-Scan/data/jobs_50_MICRO_28_Apr_15_2016",
        "/Users/robina/Dropbox/4Tau/NMSSM-Scan/data/jobs_50_MICRO_28_Apr_15_2017",
        "/Users/robina/Dropbox/4Tau/NMSSM-Scan/data/jobs_50_MICRO_28_Apr_15_2018",
    ]

    # can use either command-line input, or manually add in folders here if easier
    # note that command lien arg takes precedent
    folders = args.input if args.input else job_folders
    df_orig, df_pass_all, df_ma1Lt10, df_h1SM, df_h2SM = make_dataframes(folders)

    store = pd.HDFStore(args.output, complevel=9, comlib='bzip2')

    store.put('full12loop_all', df_orig, format='table', data_columns=True)
    store.put('full12loop_good_posMuMagMom_planckUpperOnly', df_pass_all, format='table', data_columns=True)
    store.put('full12loop_good_posMuMagMom_planckUpperOnly_maLt10', df_ma1Lt10, format='table', data_columns=True)
    store.put('full12loop_good_posMuMagMom_planckUpperOnly_h1SM', df_h1SM, format='table', data_columns=True)
    store.put('full12loop_good_posMuMagMom_planckUpperOnly_h2SM', df_h2SM, format='table', data_columns=True)

