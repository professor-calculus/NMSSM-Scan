#!/usr/bin/env python

"""
This script runs NMSSMTools over parameter ranges, with optional depenence
between parameters.

This allows for running on a batch system, where each worker node can scan
randomly over a given range, improving efficiency.
"""

import os
import sys
import argparse
import logging
import random
from glob import glob
from subprocess import call
import json
import re


logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)
log = logging.getLogger(__name__)


def NMSSMScan(in_args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card",
                        help="Input card template",
                        required=True)
    parser.add_argument("--oDir",
                        help="Output directory for spectrum/MicrOMEGAs files")
    parser.add_argument("--param",
                        help='JSON file with parameter range to run over.',
                        required=True)
    parser.add_argument('-n', '--number',
                        help='Number of points to run over',
                        type=int,
                        default=1)
    parser.add_argument("--dry",
                        help="Dry run, don't submit to queue.",
                        action='store_true')
    parser.add_argument("-v",
                        help="Display debug messages.",
                        action='store_true')

    args = parser.parse_args(args=in_args)

    if args.v:
        log.setLevel(logging.DEBUG)
        log.debug(args)

    log.debug('program args: %s' % args)

    # do some checks
    check_file_exists(args.card)
    check_file_exists(args.param)
    if args.number < 1:
        log.error('-n|--number must have an argument >= 1')
    if not args.oDir:
        # generate output directory if one not specified
        args.oDir = generate_odir_soolin()
    check_create_dir(args.oDir)

    # read template card
    with open(args.card) as template_file:
        template = template_file.readlines()

    # read in JSON file with parameters and bounds
    with open(args.param) as json_file:
        param_dict = json.load(json_file)
        # remove any comments
        rm_keys = []
        for k in param_dict.iterkeys():
            if k.startswith('_'):
                rm_keys.append(k)
        for k in rm_keys:
            log.debug('Removing entry %s' % k)
            del param_dict[k]

    # loop over number of points requested, making an input card for each
    for ind in xrange(args.number):
        # generate a random point within the range
        for v in param_dict.itervalues():
            v['value'] = random.uniform(v['min'], v['max'])

        # replace values in the card text
        # eurgh stupid string in python
        new_card_text = template[:]
        for i in range(len(new_card_text)):
            for k, v in param_dict.iteritems():
                s_match = r'(\s+\d+\s+)[\w.]+(\s+#\s%s.*)' % k
                s_repl = r'\g<1>'+str(v['value'])+'D0\g<2>'
                new_card_text[i] = re.sub(s_match, s_repl, new_card_text[i])

        # write a new card
        new_card_path = generate_new_card_path(args.oDir, args.card, ind)
        with open(new_card_path, 'w') as new_card:
            for line in new_card_text:
                new_card.write(line)

        # run NMSSMTools with the new card
        if not args.dry:
            # TODO: fix as this is so prone to error
            os.chdir(glob('NMSSMTools_*')[0])
            ntools_cmds = ['./run', new_card_path]
            log.debug(ntools_cmds)
            call(ntools_cmds)
            os.chdir('..')

        # run HiggsBounds
        if not args.dry:
            # TODO: fix as this is so prone to error
            os.chdir(glob('HiggsBounds-*')[0])
            spectr_name = new_card_path.replace('inp', 'spectr')
            hb_cmds = ['./HiggsBounds', 'LandH', 'SLHA', '5', '1', spectr_name]
            log.debug(hb_cmds)
            call(hb_cmds)
            os.chdir('..')

    # print some stats
    print '*' * 40
    print '* Num iterations:', args.number
    print '*' * 40


def check_file_exists(filename):
    """Check to see if file exists, if not raise IOError."""
    if not os.path.isfile(filename):
        raise IOError('File %s does not exist' % filename)


def check_create_dir(directory, info=False):
    """Check to see if directory exists, if not make it.

    Can optionally display message to user.
    """
    if not os.path.isdir(directory):
        if os.path.isfile(directory):
            raise RuntimeError("Cannot create directory %s, already "
                               "exists as a file object" % directory)
        os.makedirs(directory)
        if info:
            print "Making dir %s" % directory


def generate_odir_soolin():
    return '/hdfs/user/%s/NMSSM-Scan/' % (os.environ['LOGNAME'])


def generate_new_card_path(oDir, card, ind):
    """Generate a new filepath for the output card.

    oDir: str
        Output directory for card.
    card: str
        Name of the card to be used as a basis.
    ind: int
        Index to be added to end of filename.
    """
    stem = os.path.splitext(os.path.basename(card))[0]
    return os.path.join(oDir, '%s_%d.dat' % (stem, ind))


if __name__ == "__main__":
    NMSSMScan()