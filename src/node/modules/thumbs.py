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
from nodetools.ffmpeg import FFmpegHandler, FileInfo
from shutil import rmtree
import os
import re
import subprocess
import daemon
import sys
import Image
import ImageDraw


class ThumbFFmpegHandler(FFmpegHandler):
    FAST_SEEK_THRESHOLD=15
    def __init__(self, eparams ,  localfile,  outfile, frames, width, height, seek, interval):
        super(ThumbFFmpegHandler, self).__init__(eparams, localfile, outfile, frames, None)
        if interval>ThumbFFmpegHandler.FAST_SEEK_THRESHOLD: 
            self.commonargs=self.commonargs[:2]+["-ss", str(seek)]+self.commonargs[2:]
        else: 
            self.commonargs+=["-ss", str(seek)]
        self.commonargs+=[ "-s", str(width)+"x"+str(height), "-qscale","3","-vframes","1"]
        if len(eparams.extraparams)>0: this.commonargs+=eparams.extraparams.split(" ")


class ThumbsExecutor(AbstractTaskExecutor):
    def __init__(self,reporter, workflow,task):
        super(ThumbsExecutor, self).__init__(reporter, workflow, task)
        elist=EncodersList()
        self.eparams=elist.getByUuid(task.attributes["encoder"]) 
        if self.eparams==None: raise Exception("No encoder with guid "+task.attributes["encoder"])
        if self.eparams.type<>"ffmpeg_0612": raise Exception("Unknown encoder type "+self.eparams.type)
        slist=LocalStoreList()
        self.frames=1
        self.destAsset=task.attributes["srcAssetItem"]
        if task.attributes.has_key("destAssetItem"): self.destAsset=task.attributes["destAssetItem"]
        
        self.srcfile=slist.getByUuid(task.attributes["srcStore"]).findAssetFile(task.attributes["srcAssetItem"], task.attributes["srcAssetItemType"])
        self.targetdir=slist.getByUuid(task.attributes["destStore"]).findAsset(self.destAsset)
        if not os.path.exists(self.targetdir): os.makedirs(self.targetdir)
        
    def progressCb(self, progress):
        pass
    def computeSize(self, fi):
        origratio=fi.aspect
        w=self.eparams.width
        h=self.eparams.height
        newratio=float(w)/float(h)
        if origratio<newratio: w=int(h*origratio)
        else: h=int(w/origratio)
        return (w, h)

    def round_corner(self, radius, fill):
        """Draw a round corner"""
        corner = Image.new('RGBA', (radius, radius), (0, 0, 0, 0))
        draw = ImageDraw.Draw(corner)
        draw.pieslice((0, 0, radius * 2, radius * 2), 180, 270, fill=fill)
        return corner
 
    def round_rectangle(self, size, radius, fill):
        """Draw a rounded rectangle"""
        width, height = size
        rectangle = Image.new('RGBA', size, fill)
        if radius==0: return rectangle 
        corner = self.round_corner(radius, fill)
        rectangle.paste(corner, (0, 0))
        rectangle.paste(corner.rotate(90), (0, height - radius)) # Rotate the corner and paste it
        rectangle.paste(corner.rotate(180), (width - radius, height - radius))
        rectangle.paste(corner.rotate(270), (width - radius, 0))
        return rectangle
 
        
    def makeBorder(self, outfile):
        img=Image.open(outfile)
        w=self.eparams.borderWidth
        newimg=self.round_rectangle(img.size, self.eparams.borderRadius, self.eparams.borderColor)
        maskimg=Image.new("RGB", img.size, 0)
        mask=self.round_rectangle((img.size[0]-2*w, img.size[1]-2*w), self.eparams.borderRadius, 'white''')
        maskimg.paste(mask, (w, w, img.size[0]-w, img.size[1]-w))
        cropimg=img.crop((w, w, img.size[0]-w, img.size[1]-w))
        print cropimg.size,  mask.size,  maskimg.size
        newimg.paste(cropimg, (w, w, img.size[0]-w, img.size[1]-w), mask)
        newimg.save(outfile, quality=80, optimize=True)
        return
                                                      
        draw=ImageDraw.Draw(img)
        w=self.eparams.borderWidth
        fill=self.eparams.borderColor
        draw.rectangle(((0, 0), (img.size[0], w)), fill=self.eparams.borderColor) 
        draw.rectangle(((0, 0), (w, img.size[1])), fill=self.eparams.borderColor) 
        draw.rectangle((img.size, (0, img.size[1]-w)), fill=self.eparams.borderColor) 
        draw.rectangle((img.size, ( img.size[0]-w, 0)), fill=self.eparams.borderColor) 
        
        if self.eparams.borderRadius>0:
            radius=self.eparams.borderRadius
            print radius
            corner = Image.new('RGBA', (radius, radius), (0, 0, 0, 0))
            xdraw = ImageDraw.Draw(corner)
            xdraw.pieslice((0, 0, radius * 2, radius * 2), 180, 270, fill=fill)
            img.paste(corner, (0, 0))
            img.paste(corner.rotate(90), (0, w - radius)) # Rotate the corner and paste it
            img.paste(corner.rotate(180), (w - radius, w - radius))
            img.paste(corner.rotate(270), (w - radius, 0))
        img.save(outfile, quality=80, optimize=True)
        
    def run(self):
        fi=FileInfo(self.srcfile)
        self.frames=fi.frames
        (w, h)=self.computeSize(fi)
        
        nr=0
        point=0.0
        ival=self.eparams.thumbsInterval
        if ival==0: ival=float(fi.duration+1.0)/self.eparams.thumbsCount
        if ival==0: raise Exception("Wrong thumbs interval")
        while True:
            outfile=self.targetdir+"/th_"+self.destAsset+"_"+str(nr)+"."+self.eparams.outputtype
            fmpg=ThumbFFmpegHandler(self.eparams,   self.srcfile, outfile,  fi.frames, w, h, point,  ival)
            fmpg.run()
            if self.eparams.borderWidth>0: self.makeBorder(outfile)
            point+=ival
            nr+=1
            if point>=fi.duration: break
        
def pluginInfo():
    return "THUMBS", ThumbsExecutor
