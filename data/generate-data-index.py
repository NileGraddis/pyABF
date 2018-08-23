"""
This code reads every ABF in the data folder and updates its header information.
This script outputs HTML files, markdown files, and generates the readme.md in
the root folder of the data directory. It also generates thumbnails for each ABF.
"""

# import the pyabf module from this development folder
import os
import sys
PATH_HERE = os.path.abspath(os.path.dirname(__file__))
PATH_SRC = os.path.abspath(PATH_HERE+"/../src/")
PATH_DATA = os.path.abspath(PATH_HERE+"/../data/abfs/")
sys.path.insert(0, PATH_SRC)  # for importing
sys.path.append("../src/")  # for your IDE
import pyabf

import logging
logging.basicConfig(level=logging.WARNING)
log = logging.getLogger(__name__)

import datetime
import numpy as np
import matplotlib.patches as patches
import matplotlib.pyplot as plt
plt.style.use('bmh')  # alternative color scheme

# now you are free to import additional modules
import glob

sectionSizes = {'HeaderV1': 1678, 'HeaderV2': 76, 'SectionMap': 216,
                'ProtocolSection': 208, 'ADCSection': 82, 'DACSection': 132,
                'EpochPerDACSection': 30, 'EpochSection': 4, 'TagSection': 64,
                'StringsSection': 0, 'StringsIndexed': 0}


def sectionBytes(section):
    """return [firstByte, byteCount]"""
    assert len(section) == 3
    firstByte = section[0]*512
    byteCount = section[1]*section[2]
    return [firstByte, byteCount]


def plotHeader(abf):
    """create a figure showing where the header sections are."""

    byteMap = {}
    byteMap["file"] = [0, abf._fileSize-1]

    if abf.abfVersion["major"] == 1:
        byteMap["ABFheaderV1"] = [0, 4898+684]  # start byte and size
        byteMap["DataSection"] = [abf.dataByteStart,
                                  abf.dataPointByteSize*abf.dataPointCount]
    else:
        byteMap["ABFheaderV2"] = [0, 75]
        byteMap["SectionMap"] = [76, 348+16]
        byteMap["ProtocolSection"] = sectionBytes(
            abf._sectionMap.ProtocolSection)
        byteMap["ADCSection"] = sectionBytes(abf._sectionMap.ADCSection)
        byteMap["DACSection"] = sectionBytes(abf._sectionMap.DACSection)
        byteMap["EpochPerDACSection"] = sectionBytes(
            abf._sectionMap.EpochPerDACSection)
        byteMap["EpochSection"] = sectionBytes(
            abf._sectionMap.EpochSection)
        byteMap["TagSection"] = sectionBytes(abf._sectionMap.TagSection)
        byteMap["StringsSection"] = sectionBytes(
            abf._sectionMap.StringsSection)
        byteMap["DataSection"] = sectionBytes(
            abf._sectionMap.DataSection)

    fig = plt.figure(figsize=(12, 3))
    fig.patch.set_alpha(0)  # transparent background

    # LEFT SUBPLOT

    ax1 = fig.add_subplot(121)
    ax2 = fig.add_subplot(122)

    for ax in [ax1, ax2]:

        ax.patch.set_facecolor('w')
        ax.patch.set_facecolor('w')

        for i, part in enumerate(byteMap.keys()):
            firstByte, byteCount = byteMap[part]
            #lastByte = firstByte + byteCount
            color = plt.get_cmap("jet")(i/len(byteMap))
            if part == "file":
                rect = patches.Rectangle((firstByte, -.5), byteCount, .5,
                                         linewidth=0, facecolor='.5',
                                         alpha=1, label=part)
            else:
                rect = patches.Rectangle((firstByte, 0), byteCount, 1,
                                         linewidth=0, facecolor=color,
                                         alpha=1, label=part)
            ax.add_patch(rect)

        # hide the box on the edges
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_visible(False)

        plt.text(0, -.25, "  "+abf.abfID, ha='left', va='center')
        plt.xlabel("Byte Position")
        plt.margins(.1, .1)
        ax.get_yaxis().set_visible(False)  # hide Y axis
        plt.tight_layout()
        ax1.set_title("ABF Byte Map for "+abf.abfID+".abf")
        ax2.legend(loc='upper right', fontsize=8, shadow=True, framealpha=1)

    ax1.axis([-100, abf.dataByteStart+1500, -.5, 1])

    x1 = abf.dataByteStart + abf.dataPointCount*2
    x2 = abf._fileSize
    ax2.axis([x1-1500, x2+1500, -.5, 1])

    fnameOut = os.path.dirname(os.path.dirname(abf.abfFilePath))
    fnameOut += "/headers/"+abf.abfID+"_map.png"
    plt.savefig(fnameOut)
    plt.close()


def plotThumbnail(abf):
    """
    Create a graph some the DAC (command) and ADC (measure) data
    """
    # create figure and subplots
    fig = plt.figure(figsize=(8, 6))
    fig.patch.set_alpha(0)  # transparent background
    ax1 = fig.add_subplot(211)
    ax2 = fig.add_subplot(212)
    ax1.patch.set_facecolor('w')
    ax2.patch.set_facecolor('w')
    ax1.set_xmargin(0)
    ax2.set_xmargin(0)

    # overlap or continuous view depends on protocol
    absoluteTime = False
    if "0111" in abf.protocol:
        absoluteTime = True
    if "loose" in abf.protocol:
        absoluteTime = True

    # usually we plot channel 0, but sometimes manually override
    channel = 0
    if "18702001" in abf.abfID:
        channel = 1

    # plot the data sweep by sweep
    for sweep in abf.sweepList:
        abf.setSweep(sweep, channel=channel, absoluteTime=absoluteTime)
        ax1.plot(abf.sweepX, abf.sweepY, alpha=.5, color='b', lw=.5)
        ax2.plot(abf.sweepX, abf.sweepC, color='r')

    # decorate plot and save it
    ax1.set_title("{}.abf [channel: {}/{}] [sweeps: {}]".format(
        abf.abfID, abf.sweepChannel+1, abf.channelCount, abf.sweepNumber+1))
    ax1.set_ylabel(abf.sweepLabelY)
    ax1.set_xlabel(abf.sweepLabelX)
    ax2.set_ylabel(abf.sweepLabelC)
    ax2.set_xlabel(abf.sweepLabelX)
    fig.tight_layout()
    fig.savefig(PATH_HERE+"/../data/headers/%s.png" % abf.abfID)
    plt.close()


def go():

    print("Generating data index page", end=" ")

    md = "# Sample ABFs\n\n"
    md += "This is a small collection of various ABFs I practice developing with. "
    md += "Many of them were emailed to me by contributors. If you have a unique type "
    md += "of ABF file, email it to me and I will include it here. Note that this page "
    md += "is generated automatically by [generate-data-index.py](generate-data-index.py).\n\n"

    md += "ABF Information | Header Map | Thumbnails\n"
    md += "---|---|---\n"

    for fname in sorted(glob.glob(PATH_DATA+"/*.abf")):

        # load the ABF
        abf = pyabf.ABF(fname)

        # indicate which ABF is being challenged
        log.debug("creating thumbnail for %s" % abf.abfID)

        # create the graphs
        plotThumbnail(abf)
        plotHeader(abf)
        print(".", end="")
        sys.stdout.flush()

        # update main readme
        abfIDsafe = abf.abfID.replace(" ","%20")
        md += f"**{abf.abfID}.abf**<br />"
        md += f"ABF Version: {abf.abfVersionString}<br />"
        md += "Channels: %d (%s)<br />" % (abf.channelCount,
                                           ", ".join(abf.adcUnits))
        md += f"Sweeps: {abf.sweepCount}<br />"
        md += f"Protocol: _{abf.protocol}_"
        md += " | "
        md += "![headers/%s_map.png](headers/%s_map.png)<br />" % (
            abfIDsafe, abfIDsafe)
        md += "[view entire header](headers/%s.md)" % (abfIDsafe)
        md += " | "
        md += "![headers/%s.png](headers/%s.png)" % (abfIDsafe, abfIDsafe)
        md += "\n"

    # write main readme
    with open(PATH_HERE+"/../data/readme.md", 'w') as f:
        f.write(md)

    print(" OK")


if __name__ == "__main__":
    go()
