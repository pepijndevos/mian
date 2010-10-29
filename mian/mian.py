#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""mian - Mine analysis - Graph block types to height in a Minecraft save game
<http://github.com/l0b0/mian>

Default syntax:

mian [-b|--blocks=<list>] [-l|--list] [-o|--output=path] <World directory>

Options:

-b, --blocks    Specify block types to include as a comma-separated list, using
                either the block_names or hex values from the list.
-l, --list      List available block types (from
                <http://www.minecraftwiki.net/wiki/Data_values>).
-o, --output    Output file name, defaults to WorldX.png.

Description:

Creates a file with a graph of how much the given materials occur at each
layer of the map.

Examples:

$ mian ~/.minecraft/saves/World1
Creates World1.png in the current directory with the graph.

$ mian --blocks="diamond ore,mob spawner,obsidian" ~/.minecraft/saves/World1
Ditto, showing only the specified block types

$ mian --list
Show a list of block types that can be searched for
"""

__author__ = 'Pepijn de Vos, Victor Engmark'
__copyright__ = 'Copyright (C) 2010 Pepijn de Vos, Victor Engmark'
__credits__ = ['Pepijn de Vos', 'Victor Engmark']
__maintainer__ = 'Victor Engmark'
__email__ = 'victor.engmark@gmail.com'
__license__ = 'GPL v3 or newer'

from binascii import unhexlify
from getopt import getopt, GetoptError
from glob import glob
import Gnuplot
from itertools import izip
from nbt.nbt import NBTFile
from os.path import join, split
from signal import signal, SIGPIPE, SIG_DFL
from string import hexdigits
import sys
import warnings

ARG_ERROR = 'You need to specify exactly one save directory.'

BLOCK_TYPES = {
    '\x00': 'Air',
    '\x01': 'Stone',
    '\x02': 'Grass',
    '\x03': 'Dirt',
    '\x04': 'Cobblestone',
    '\x05': 'Wood',
    '\x06': 'Sapling',
    '\x07': 'Bedrock',
    '\x08': 'Water',
    '\x09': 'Stationary water',
    '\x0a': 'Lava',
    '\x0b': 'Stationary lava',
    '\x0c': 'Sand',
    '\x0d': 'Gravel',
    '\x0e': 'Gold ore',
    '\x0f': 'Iron ore',
    '\x10': 'Coal ore',
    '\x11': 'Log',
    '\x12': 'Leaves',
    '\x13': 'Sponge',
    '\x14': 'Glass',
    '\x15': 'Red cloth',
    '\x16': 'Orange cloth',
    '\x17': 'Yellow cloth',
    '\x18': 'Lime cloth',
    '\x19': 'Green cloth',
    '\x1a': 'Aqua green cloth',
    '\x1b': 'Cyan cloth',
    '\x1c': 'Blue cloth',
    '\x1d': 'Purple cloth',
    '\x1e': 'Indigo cloth',
    '\x1f': 'Violet cloth',
    '\x20': 'Magenta cloth',
    '\x21': 'Pink cloth',
    '\x22': 'Black cloth',
    '\x23': 'Gray / white cloth',
    '\x24': 'White cloth',
    '\x25': 'Yellow flower',
    '\x26': 'Red rose',
    '\x27': 'Brown mushroom',
    '\x28': 'Red mushroom',
    '\x29': 'Gold block',
    '\x2a': 'Iron block',
    '\x2b': 'Double step',
    '\x2c': 'Step',
    '\x2d': 'Brick',
    '\x2e': 'TNT',
    '\x2f': 'Bookshelf',
    '\x30': 'Mossy cobblestone',
    '\x31': 'Obsidian',
    '\x32': 'Torch',
    '\x33': 'Fire',
    '\x34': 'Mob spawner',
    '\x35': 'Wooden stairs',
    '\x36': 'Chest',
    '\x37': 'Redstone wire',
    '\x38': 'Diamond ore',
    '\x39': 'Diamond block',
    '\x3a': 'Workbench',
    '\x3b': 'Crops',
    '\x3c': 'Soil',
    '\x3d': 'Furnace',
    '\x3e': 'Burning furnace',
    '\x3f': 'Sign post',
    '\x40': 'Wooden door',
    '\x41': 'Ladder',
    '\x42': 'Minecart tracks',
    '\x43': 'Cobblestone stairs',
    '\x44': 'Wall sign',
    '\x45': 'Lever',
    '\x46': 'Stone pressure plate',
    '\x47': 'Iron door',
    '\x48': 'Wooden pressure plate',
    '\x49': 'Redstone ore',
    '\x4a': 'Glowing redstone ore',
    '\x4b': 'Redstone torch (off)',
    '\x4c': 'Redstone torch (on)',
    '\x4d': 'Stone button',
    '\x4e': 'Snow',
    '\x4f': 'Ice',
    '\x50': 'Snow block',
    '\x51': 'Cactus',
    '\x52': 'Clay',
    '\x53': 'Reed',
    '\x54': 'Jukebox',
    '\x55': 'Fence'}

DEFAULT_BLOCK_TYPES = [
    'Clay',
    'Coal ore',
    'Diamond ore',
    'Gold ore',
    'Iron ore',
    'Obsidian',
    'Redstone ore']

CHUNK_SIZE_Y = 128
CHUNK_SIZE_Z = 16
CHUNK_SIZE_X = CHUNK_SIZE_Y * CHUNK_SIZE_Z

signal(SIGPIPE, SIG_DFL)
"""Avoid 'Broken pipe' message when canceling piped command."""


def _lookup_block_type(block_type):
    """
    Find block types based on input string.

    @param block_type: Name or hex ID of a block type.
    @return: Subset of BLOCK_TYPES.
    """

    if block_type is None or len(block_type) == 0:
        warnings.warn('Empty block type')
        return None

    block_type = block_type.lower()

    if len(block_type) == 2 and all(char in hexdigits for char in block_type):
        # Look up single block type by hex value
        for key, value in BLOCK_TYPES.iteritems():
            if key == unhexlify(block_type):
                return {key: value}

    # Name substring search
    result = {}
    for key, value in BLOCK_TYPES.iteritems():
        if value.lower().find(block_type) != -1:
            result[key] = BLOCK_TYPES[key]

    if result == []:
        warnings.warn('Unknown block type %s' % block_type)
    return result


def print_block_types():
    """Print the block block_names and hexadecimal IDs"""
    for key, value in BLOCK_TYPES.iteritems():
        print hex(ord(key))[2:].upper().zfill(2), value


def mian(world_dir, output_file, block_types):
    """
    Runs through the DAT files and creates the output.

    @param world_dir: Path to existing Minecraft world directory.
    @param output_file: Path to file which should be written.
    @param block_types: Subset of BLOCK_TYPES.
    """
    paths = glob(join(world_dir, '*/*/*.dat')) # All world blocks

    xyz_values = []

    # Unpack block format
    # <http://www.minecraftwiki.net/wiki/Alpha_Level_Format#Block_Format>
    for path in paths:
        nbtfile = NBTFile(path,'rb')

        yzx_block = nbtfile["Level"]["Blocks"].value

        yzx_block_list = [iter(yzx_block)]

        xyz_block = izip(
                *yzx_block_list * CHUNK_SIZE_Y)

        xyz_values.extend(xyz_block)

        nbtfile.file.close()

    zxy_values = izip(*xyz_values)

    bt_hexes = block_types.keys()
    bt_names = block_types.values()

    def count_block_types(layer):
        def filter_block(bname):
            return len([block for block in layer if block == bname])

        return map(filter_block, bt_hexes)

    y_counts = []
    for layer in zxy_values:
        y_counts.append(count_block_types(layer))

    data = izip(*y_counts)
    print data

    gnuplot = Gnuplot.Gnuplot()
    gnuplot('set term png')
    gnuplot('set out "%s"' % output_file)
    gnuplot('set style data lines')

    plot_data = (
        Gnuplot.PlotItems.Data(
            list(enumerate(block)),
            title=bt_names[index]) for index, block in enumerate(data))

    gnuplot.plot(*plot_data)


def main(argv = None):
    """Argument handling."""

    if argv is None:
        argv = sys.argv

    # Defaults
    block_block_names = DEFAULT_BLOCK_TYPES
    output_file = None

    try:
        opts, args = getopt(
            argv[1:],
            'b:lo:',
            ['blocks=', 'list', 'output='])
    except GetoptError, err:
        sys.stderr.write(str(err) + '\n')
        return 2

    for option, value in opts:
        if option in ('-b', '--blocks'):
            block_block_names = value.split(',')
        elif option in ('-l', '--list'):
            print_block_types()
            return 0
        elif option in ('-o', '--output'):
            output_file = value

    assert len(args) == 1, ARG_ERROR
    world_dir = args[0]

    if output_file is None:
        # Use savegame directory name
        output_file = split(world_dir)[1] + '.png'

    # Look up block_types
    block_types = {}
    for name in block_block_names:
        block_types.update(_lookup_block_type(name))

    mian(world_dir, output_file, block_types)


if __name__ == '__main__':
    sys.exit(main())