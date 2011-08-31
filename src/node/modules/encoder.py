##
## This file is part of the Styk.TV API project.
##
## Copyright (c) 2011 Piotr Styk (peter@styk.tv)
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License version 2 
## as published by  the Free Software Foundation
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
##


from nodetools.xmlqueue import XMLJobManager
from nodetools.abstractqueue import AbstractTaskExecutor,Queue, ST_WORKING
from nodetools.encoderlist import EncodersList
from nodetools.localstores import LocalStoreList
from nodetools.ffmpeg import FFmpegHandler, FileInfo,  getFFPath
from shutil import rmtree
from nodetools.config import Config
import os
import re
import subprocess
import daemon
import sys


class VideoFFmpegHandler(FFmpegHandler):
    def __init__(this, eparams ,  localfile,  outfile, frames, progressCb):
        super(VideoFFmpegHandler, this).__init__(eparams, localfile, outfile, frames, progressCb)
        this.commonargs+=[ "-vcodec", this.eparams.vcodec]
        if len(eparams.extraparams)>0: this.commonargs+=eparams.extraparams.split(" ")
        if this.eparams.fps>0: this.commonargs+=["-r", str(this.eparams.fps)]
        if this.eparams.width>0 and this.eparams.height>0: this.commonargs+=["-s", str(this.eparams.width)+"x"+str(this.eparams.height)]
        this.commonargs+=this.handleWatermark()
        
            
        this.commonargs+=[ "-b", str(this.eparams.bitrate)]
        this.commonargs+=["-acodec", this.eparams.acodec, "-ac","2","-ar", "44100", "-ab",str(this.eparams.audiobitrate)]
    def handleWatermark(this):
        fps=None
        if this.eparams.watermarkFile<>"":
            path=Config.CONFIGDIR+"/"+this.eparams.watermarkFile
        elif this.eparams.watermarkAsset<>"":
            slist=LocalStoreList()
            store=slist.getByUuid(this.eparams.watermarkStore)
            (ext, fps)=store.decodeAssetType(this.eparams.watermarkAssetType)
            path=getFFPath(store, this.eparams.watermarkAsset, this.eparams.watermarkAssetType)
        if fps==None: return this.handleSingleWatermark(path)
        else: return this.handleAnimatedWatermark(path, fps)

    def handleSingleWatermark(this, path):
            filter="movie="+path+" [wm]; [in][wm] overlay="+str(this.eparams.watermarkX)+":"+str(this.eparams.watermarkY)+" [out]"
            return ["-vf", filter]
    def handleAnimatedWatermark(this, path, fps):
            filter="setpts=PTS-STARTPTS [main]; movie="+path+" [wm];[wm]settb=1[wm];[wm]setpts="+str(this.eparams.watermarkStart)+"*TB+N/("+str(fps)+"*TB)[wm];[main][wm] overlay="+str(this.eparams.watermarkX)+":"+str(this.eparams.watermarkY)+ " [out]"
            return ["-vf", filter]
        
        
        


class EncoderExecutor(AbstractTaskExecutor):
    def __init__(self,reporter, workflow,task):
        super(EncoderExecutor, self).__init__(reporter, workflow, task)
        elist=EncodersList()
        self.eparams=elist.getByUuid(task.attributes["encoder"]) 
        if self.eparams==None: raise Exception("No encoder with guid "+task.attributes["encoder"])
        if self.eparams.type<>"ffmpeg_0612": raise Exception("Unknown encoder type "+self.eparams.type)
        slist=LocalStoreList()
        self.frames=1
        dstAsset=task.attributes["srcAssetItem"]
        if task.attributes.has_key("destAssetItem"): dstAsset=task.attributes["destAssetItem"]

        self.srcfile=slist.getByUuid(task.attributes["srcStore"]).findAssetFile(task.attributes["srcAssetItem"], task.attributes["srcAssetItemType"])
        targetdir=slist.getByUuid(task.attributes["destStore"]).findAsset(dstAsset)
        if not os.path.exists(targetdir): os.makedirs(targetdir)
        self.outfile=slist.getByUuid(task.attributes["destStore"]).findAssetFile(dstAsset, self.eparams.outputtype)
        
    def progressCb(self, progress):
        self.reporter.setQueueProperty(self.workflow, self.task, "frame", str(progress))
        self.updateProgress(progress*100.0/self.frames)
 #       self.reporter.setQueueProperty(self.workflow, self.task, "progress",  "%.2f" % (progress*100.0/self.frames))
    def run(self):
        fi=FileInfo(self.srcfile)
        self.frames=fi.frames
        self.reporter.setQueueProperty(self.workflow, self.task, "all_frames", str(fi.frames))
        
        fmpg=VideoFFmpegHandler(self.eparams,   self.srcfile, self.outfile,  fi.frames, self.progressCb)
        fmpg.run()
        
def pluginInfo():
    return "ENCODE", EncoderExecutor
