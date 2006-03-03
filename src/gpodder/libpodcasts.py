
#
# gPodder
# Copyright (c) 2005 Thomas Perl <thp@perli.net>
# Released under the GNU General Public License (GPL)
#

#
#  libpodcasts.py -- data classes for gpodder
#  thomas perl <thp@perli.net>   20051029
#
#

import gtk
import gobject

import libgpodder

from os.path import exists

from liblocdbwriter import writeLocalDB
from liblocdbreader import readLocalDB

from threading import Event
from libwget import downloadThread
import re

class podcastChannel(object):
    """holds data for a complete channel"""
    def __init__( self, url = "", title = "", link = "", description = ""):
        self.url = url
        self.title = title
        self.link = link
        self.description = stripHtml( description)
        self.items = []
        self.image = None
        self.shortname = None
        self.downloaded = None
        self.__filename = None
        self.__download_dir = None
        
    # Create all the properties
    def get_filename(self):
        if self.__filename == None:
            self.__filename = ""

            for char in self.title.lower():
                if (char >= 'a' and char <= 'z') or (char >= 'A' and char <= 'Z') or (char >= '1' and char <= '9'):
                    self.__filename = self.__filename + char
                    
        if self.__filename == "":
            self.__filename = "__unknown__"

        return self.__filename

    def set_filename(self, value):
        self.__filename = value
        
    filename = property(fget=get_filename,
                        fset=set_filename)
    
    def addItem( self, item):
        self.items.append( item)

    def addDownloadedItem( self, item):
        localdb = libgpodder.gPodderLib().getChannelIndexFile( self)
        if libgpodder.isDebugging():
            print "localdb: " + localdb

        try:
            locdb_reader = readLocalDB()
            locdb_reader.parseXML( localdb)
            self.downloaded = locdb_reader.channel
        except:
            print "no local db found or local db error: creating new.."
            self.downloaded = podcastChannel( self.url, self.title, self.link, self.description)
        
        self.downloaded.items.append( item)
        writeLocalDB( localdb, self.downloaded)
    
    def printChannel( self):
        print '- Channel: "' + self.title + '"'
        for item in self.items:
            print '-- Item: "' + item.title + '"'

    def isDownloaded( self, item):
        return libgpodder.gPodderLib().podcastFilenameExists( self, item.url)

    def getItemsModel( self):
        new_model = gtk.ListStore( gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_BOOLEAN, gobject.TYPE_STRING)

        for item in self.items:
            # Skip items with no download url
            if item.url != "":
                if self.isDownloaded(item):
                    background_color = "#eeeeee"
                else:
                    background_color = "white"
                new_iter = new_model.append()
                new_model.set( new_iter, 0, item.url)
                new_model.set( new_iter, 1, item.title)
                new_model.set( new_iter, 2, item.getSize())
                new_model.set( new_iter, 3, True)
                new_model.set( new_iter, 4, background_color)
        
        return new_model
    
    def getActiveByUrl( self, url):
        i = 0
        
        for item in self.items:
            if item.url == url:
                return i
            i = i + 1

        return -1

    def downloadRss( self, force_update = True):
        
        if (self.filename == "__unknown__" or exists( self.cache_file) == False) or force_update:
            event = Event()
            downloadThread(self.url, self.cache_file, event).download()
            
            while event.isSet() == False:
                event.wait( 0.2)
                #FIXME: we do not want gtk code when not needed
                while gtk.events_pending():
                    gtk.main_iteration( False)
        
        return self.cache_file
    
    def get_save_dir(self):
        savedir = self.download_dir + self.filename + "/"
        libgpodder.gPodderLib().createIfNecessary( savedir)
        return savedir
    
    save_dir = property(fget=get_save_dir)

    def get_download_dir(self):
        print "get download dir:", self, self.__download_dir
        if self.__download_dir == None:
            return libgpodder.gPodderLib().downloaddir
        else:
            return self.__download_dir

    def set_download_dir(self, value):
        self.__download_dir = value
        libgpodder.gPodderLib().createIfNecessary(self.__download_dir)
        print "set download dir:", self, self.__download_dir        
        
    download_dir = property (fget=get_download_dir,
                             fset=set_download_dir)

    def get_cache_file(self):
        return libgpodder.gPodderLib().cachedir + self.filename + ".xml"

    cache_file = property(fget=get_cache_file)
    
    def get_index_file(self):
        # gets index xml filename for downloaded channels list
        return self.save_dir + "index.xml"
    
    index_file = property(fget=get_index_file)

class podcastItem(object):
    """holds data for one object in a channel"""
    def __init__( self,
                  url = "",
                  title = "",
                  length = "0",
                  mimetype = "",
                  guid = "",
                  description = "",
                  link = ""):
        self.url = url
        self.title = title
        self.length = length
        self.mimetype = mimetype
        self.guid = guid
        self.description = stripHtml( description)
        self.link = ""
    
    def getSize( self):
        kilobyte = 1024
        megabyte = kilobyte * 1024
        gigabyte = megabyte * 1024

        size = int( self.length)
        if size > gigabyte:
            return str( size / gigabyte) + " GB"
        if size > megabyte:
            return str( size / megabyte) + " MB"
        if size > kilobyte:
            return str( size / kilobyte) + " KB"

        return str( size) + " Bytes"

def channelsToModel( channels):
    new_model = gtk.ListStore( gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_OBJECT)
    
    for channel in channels:
        new_iter = new_model.append()
        new_model.set( new_iter, 0, channel.url)
        new_model.set( new_iter, 1, channel.title + " ("+channel.url+")")
        #if channel.image != None:
        #    new_model.set( new_iter, 2, gtk.gdk.pixbuf_new_from_file_at_size( channel.image, 60, 60))
        #else:
        #    new_model.set( new_iter, 2, None)
    
    return new_model

def stripHtml( html):
    # strips html from a string (fix for <description> tags containing html)
    rexp = re.compile( "<[^>]*>")
    return rexp.sub( "", html)
