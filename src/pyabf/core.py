"""
This file contains the core ABF handling class and supporting functions.
All code in this script should identically support ABF1 and ABF2 files.

Nothing the user will interact with directly is in this file.
"""

import os
import glob
import time
import datetime
import numpy as np

from pyabf.structures import HeaderV1
from pyabf.structures import HeaderV2
from pyabf.structures import SectionMap
from pyabf.structures import ProtocolSection
from pyabf.structures import ADCSection
from pyabf.structures import DACSection
from pyabf.structures import EpochPerDACSection
from pyabf.structures import EpochSection
from pyabf.structures import TagSection
from pyabf.structures import StringsSection
from pyabf.structures import StringsIndexed
import pyabf.text


class ABFcore:
    """
    The ABFcore class provides direct access to contents of ABF files.
    This class provides a common framework to access header and data values
    from ABF1 and ABF2 files.

    The input ABF could be a path to an ABF file or another ABFcore class.

    If preLoadData is enabled, all data in the ABF is read from disk and
    scaled at instantiation. In practice this is almost always the fastest way
    to work with ABFs (modern computers can easily float the data in memory).
    However, it can be disabled for projects which only read ABF headers.

    Immediately after instantiating, it is expected you will call the
    _loadEverything function.
    """

    def __init__(self, abf, preLoadData=True):
        self._loadEverything(abf, preLoadData)

    def _loadEverything(self, abf, preLoadData):
        """
        This used to be the __init__ of the ABF class.
        """
        self.abfFilePath = os.path.abspath(abf)
        assert os.path.exists(self.abfFilePath)
        self.abfID = os.path.splitext(os.path.basename(self.abfFilePath))[0]
        self._fileOpen()
        self._determineAbfFormat()
        self._readHeaders()
        self._formatVersion()
        self._determineCreationDateTime()
        self._determineDataProperties()
        self._determineDataUnits()
        self._determineDataScaling()
        self._determineHoldingValues()
        self._determineProtocolPath()
        self._determineProtocolComment()
        self._makeTagTimesHumanReadable()
        if preLoadData:
            self._loadAndScaleData()
        self._fileClose()

    def _fileOpen(self):
        """Open the ABF file in rb mode."""
        self._fb = open(self.abfFilePath, 'rb')
        self._fileOpenTime = time.perf_counter()

    def _determineAbfFormat(self):
        """
        The first few characters of an ABF file tell you its format.
        "ABF " is for ABF1 files, and "ABF2" is for ABF2 files.
        Anything else is probably a file that's not actually an ABF.
        """
        self._fb.seek(0)
        code = self._fb.read(4)
        code = code.decode("ascii", errors='ignore')
        if code == "ABF ":
            self.abfFileFormat = 1
        elif code == "ABF2":
            self.abfFileFormat = 2
        else:
            raise NotImplementedError("Not a valid ABF1 or ABF2 file!")

    def _fileClose(self):
        """
        Close the ABF file. Releasing it allows it to be read by ClampFit. 
        Clampfit, regrettably, is a file-access-blocking data viewer.
        """
        self._fileCloseTime = time.perf_counter()
        self._fb.close()
        self._dataLoadTimeMs = (self._fileCloseTime-self._fileOpenTime)*1000

    def _readHeaders(self):
        """
        Read all headers into memory. 
        Store them in variables that can be accessed at any time.
        """
        if self.abfFileFormat == 1:
            self._headerV1 = HeaderV1(self._fb)
        elif self.abfFileFormat == 2:
            self._headerV2 = HeaderV2(self._fb)
            self._sectionMap = SectionMap(self._fb)
            self._protocolSection = ProtocolSection(self._fb, self._sectionMap)
            self._adcSection = ADCSection(self._fb, self._sectionMap)
            self._dacSection = DACSection(self._fb, self._sectionMap)
            self._epochPerDacSection = EpochPerDACSection(
                self._fb, self._sectionMap)
            self._epochSection = EpochSection(self._fb, self._sectionMap)
            self._tagSection = TagSection(self._fb, self._sectionMap)
            self._stringsSection = StringsSection(self._fb, self._sectionMap)
            self._stringsIndexed = StringsIndexed(
                self._headerV2, self._protocolSection, self._adcSection,
                self._dacSection, self._stringsSection)
        else:
            raise NotImplementedError("Invalid ABF file format")

    def _formatVersion(self):
        """
        The ABF Version differs in format from ABF1 and ABF2.
        This function formats the version as x.x.x.x for all ABF files.
        """
        if self.abfFileFormat == 1:
            self.abfVersion = "%.03f" % self._headerV1.fFileVersionNumber
            self.abfVersion = list(self.abfVersion.replace(".", ""))
            self.abfVersion = ".".join(self.abfVersion)
        elif self.abfFileFormat == 2:
            self.abfVersion = self._headerV2.fFileVersionNumber[::-1]
            self.abfVersion = [str(x) for x in self.abfVersion]
            self.abfVersion = ".".join(self.abfVersion)
        else:
            raise NotImplementedError("Invalid ABF file format")

    def _determineCreationDateTime(self):
        """
        Determine when the ABF was recorded. This is stored in the header of
        ABF2 files, but is just the system file creation date of ABF1 files.
        """
        if self.abfFileFormat == 1:
            # use the time the ABF file was created on disk
            self.abfDateTime = round(os.path.getctime(self.abfFilePath))
            self.abfDateTime = datetime.datetime.fromtimestamp(
                self.abfDateTime)
        elif self.abfFileFormat == 2:
            # use file creation time stored in ABF header
            startDate = str(self._headerV2.uFileStartDate)
            startTime = round(self._headerV2.uFileStartTimeMS/1000)
            startDate = datetime.datetime.strptime(startDate, "%Y%M%d")
            startTime = datetime.timedelta(seconds=startTime)
            self.abfDateTime = startDate+startTime
        else:
            raise NotImplementedError("Invalid ABF file format")

    def _determineDataProperties(self):
        """
        Read the header to determine information about the signal data.
        This includes things like data rate, number of channels, number
        of sweeps, etc.
        """
        if self.abfFileFormat == 1:
            self.dataByteStart = self._headerV1.lDataSectionPtr*512
            self.dataByteStart += self._headerV1.nNumPointsIgnored
            self.dataPointCount = self._headerV1.lActualAcqLength
            self.dataChannelCount = self._headerV1.nADCNumChannels
            self.dataRate = int(1e6 / self._headerV1.fADCSampleInterval)
            self.dataSecPerPoint = 1/self.dataRate
            self.sweepCount = self._headerV1.lActualEpisodes
            if self.sweepCount == 0:  # gap free file
                self.sweepCount = 1
            self.sweepPointCount = int(self.dataPointCount / self.sweepCount)
            self.sweepLengthSec = self.sweepPointCount / self.dataRate
        elif self.abfFileFormat == 2:
            self.dataByteStart = self._sectionMap.DataSection[0]*512
            self.dataPointCount = self._sectionMap.DataSection[2]
            self.dataChannelCount = self._sectionMap.ADCSection[2]
            self.dataRate = int(
                1e6 / self._protocolSection.fADCSequenceInterval)
            self.dataSecPerPoint = 1/self.dataRate
            self.sweepCount = self._headerV2.lActualEpisodes
            if self.sweepCount == 0:  # gap free file
                self.sweepCount = 1
            self.sweepPointCount = int(self.dataPointCount / self.sweepCount)
            self.sweepLengthSec = self.sweepPointCount / self.dataRate
        else:
            raise NotImplementedError("Invalid ABF file format")

    def _determineDataUnits(self):
        """
        Channel units and names are stored in the strings section as indexed
        strings where the indexes are scattered around the header. This function
        organizes channel units and names into simple lists of strings.
        """
        if self.abfFileFormat == 1:
            self.adcUnits = self._headerV1.sADCUnits[:self.dataChannelCount]
            self.adcNames = self._headerV1.sADCChannelName[:self.dataChannelCount]
            self.dacUnits = ["?" for x in self.adcUnits]
            self.dacNames = ["?" for x in self.adcUnits]
        elif self.abfFileFormat == 2:
            self.adcUnits = self._stringsIndexed.lADCUnits[:self.dataChannelCount]
            self.adcNames = self._stringsIndexed.lADCChannelName[:self.dataChannelCount]
            self.dacUnits = self._stringsIndexed.lDACChannelUnits[:self.dataChannelCount]
            self.dacNames = self._stringsIndexed.lDACChannelName[:self.dataChannelCount]
        else:
            raise NotImplementedError("Invalid ABF file format")

    def _determineDataScaling(self):
        """
        Because data is stored as int16 values in the ABF file, after it is read
        out of the file it must be scaled to floating-point values which match
        the units. Scaling data may be different by channel, and this section
        reads the header to determine how to scale each channel.
        """
        if self.abfFileFormat == 1:
            self.scaleFactors = [1]*self.dataChannelCount
            for i in range(self.dataChannelCount):
                self.scaleFactors[i] = self._headerV1.lADCResolution/1e6
        elif self.abfFileFormat == 2:
            self.scaleFactors = [1]*self.dataChannelCount
            for i in range(self.dataChannelCount):
                self.scaleFactors[i] /= self._adcSection.fInstrumentScaleFactor[i]
                self.scaleFactors[i] /= self._adcSection.fSignalGain[i]
                self.scaleFactors[i] /= self._adcSection.fADCProgrammableGain[i]
                if self._adcSection.nTelegraphEnable:
                    self.scaleFactors[i] /= self._adcSection.fTelegraphAdditGain[i]
                self.scaleFactors[i] *= self._protocolSection.fADCRange
                self.scaleFactors[i] /= self._protocolSection.lADCResolution
                self.scaleFactors[i] += self._adcSection.fInstrumentOffset[i]
                self.scaleFactors[i] -= self._adcSection.fSignalOffset[i]
        else:
            raise NotImplementedError("Invalid ABF file format")

    def _determineHoldingValues(self):
        """
        When an ABF isn't being driven by an epoch (protocol), its command
        values are clamped at a certain holding value. This section looks-up
        those values.
        """
        if self.abfFileFormat == 1:
            self.holdingCommand = self._headerV1.fEpochInitLevel
        elif self.abfFileFormat == 2:
            self.holdingCommand = self._dacSection.fDACHoldingLevel
        else:
            raise NotImplementedError("Invalid ABF file format")

    def _determineProtocolPath(self):
        """
        If the ABF was recorded from a saved protocol, that path is stored in
        the ABF header.
        """
        if self.abfFileFormat == 1:
            self.protocolPath = self._headerV1.sProtocolPath
            self.protocol = os.path.basename(self.protocolPath)
            self.protocol = os.path.splitext(self.protocol)[0]
        elif self.abfFileFormat == 2:
            self.protocolPath = self._stringsIndexed.uProtocolPath
            self.protocol = os.path.basename(self.protocolPath)
            self.protocol = os.path.splitext(self.protocol)[0]
        else:
            raise NotImplementedError("Invalid ABF file format")

    def _determineProtocolComment(self):
        """
        ABF2 files give the user the option to store a comment when in the
        waveform editor section. This is stored in the header.
        """
        if self.abfFileFormat == 1:
            self.abfFileComment = ""  # not supported in ABF1
        elif self.abfFileFormat == 2:
            self.abfFileComment = self._stringsIndexed.lFileComment
        else:
            raise NotImplementedError("Invalid ABF file format")

    def _makeTagTimesHumanReadable(self):
        """
        Tags are comments placed at specific time points in ABF files. 
        Unfortunately the time code (lTagTime) isn't in useful unit. This 
        section converts tag times into human-readable units (like seconds).
        """
        if self.abfFileFormat == 1:
            self.tagComments = []
            self.tagTimesSec = []
            self.tagTimesMin = []
            self.tagSweeps = []
        elif self.abfFileFormat == 2:
            self.tagComments = self._tagSection.sComment
            self.tagTimesSec = self._tagSection.lTagTime
            mult = self._protocolSection.fSynchTimeUnit/1e6
            self.tagTimesSec = [mult*x for x in self.tagTimesSec]
            self.tagTimesMin = [x/60 for x in self.tagTimesSec]
            self.tagSweeps = [x/self.sweepLengthSec for x in self.tagTimesSec]
        else:
            raise NotImplementedError("Invalid ABF file format")

    def _loadAndScaleData(self):
        """
        Actual electrophysiology data is stored in the DataSection of ABF files
        as 16-bit integers. This section reads those integers into a numpy
        array, reshapes them into a 2D array (each channel is a row), and
        scales them by multiplying each channel by its scaling factor.

        To access data sweep by sweep, write your own class function! 
        That's outside the scope of this core ABF class.
        """

        self._fb.seek(self.dataByteStart)
        raw = np.fromfile(self._fb, dtype=np.int16, count=self.dataPointCount)
        raw = np.reshape(
            raw, (int(len(raw)/self.dataChannelCount), self.dataChannelCount))
        raw = np.rot90(raw)
        self.data = np.empty(raw.shape, dtype='float32')
        for i in range(self.dataChannelCount):
            self.data[i] = np.multiply(
                raw[i], self.scaleFactors[i], dtype='float32')
