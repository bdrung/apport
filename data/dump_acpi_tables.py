#!/usr/bin/python

import os, sys
from stat import *
from tempfile import mkstemp

def dump_acpi_table(filename, tablename, out):
    '''Dump a single ACPI table'''

    out.write('%s @ 0x00000000\n' % tablename)
    n = 0
    f = open(filename, 'rb')
    try:
        byte = f.read(1)
        while byte != '':
            val = ord(byte)
            if (n & 15) == 0:
                hex_str = '  %4.4x: ' % n
                ascii_str=''
                
            hex_str = hex_str + '%2.2x ' % val

            if (val < 32) or (val > 126):
                ascii_str = ascii_str + '.'
            else:
                ascii_str = ascii_str + byte
            n = n + 1
            if (n & 15) == 0:
                out.write('%s %s\n' % (hex_str, ascii_str))
            byte = f.read(1)
    finally:
        for i in range(n & 15,16):
            hex_str = hex_str + '   '

        if (n & 15) != 15:
            out.write('%s %s\n' % (hex_str, ascii_str))
        f.close()
    out.write('\n')
    
def dump_acpi_tables(path, out):
    '''Dump ACPI tables'''

    tables = os.listdir(path)
    for tablename in tables:
        pathname = os.path.join(path, tablename)
        mode = os.stat(pathname)[ST_MODE]   
        if S_ISDIR(mode):
            dump_acpi_tables(pathname, out)
        else:
            dump_acpi_table(pathname, tablename, out)

dump_acpi_tables('/sys/firmware/acpi/tables', sys.stdout)