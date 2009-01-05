# -*- coding: utf-8 -*-
#
# gPodder - A media aggregator and podcast client
# Copyright (c) 2005-2008 Thomas Perl and the gPodder Team
#
# gPodder is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# gPodder is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import gtk
import gtk.gdk
import gobject
import pango
import sys
import shutil
import subprocess
import glob
import time
import urllib
import urllib2
import datetime

from xml.sax import saxutils

from threading import Event
from threading import Thread
from threading import Semaphore
from string import strip

import gpodder
from gpodder import util
from gpodder import opml
from gpodder import services
from gpodder import sync
from gpodder import download
from gpodder import SimpleGladeApp
from gpodder import my
from gpodder.liblogger import log
from gpodder.dbsqlite import db
from gpodder import resolver

try:
    from gpodder import trayicon
    have_trayicon = True
except Exception, exc:
    log('Warning: Could not import gpodder.trayicon.', traceback=True)
    log('Warning: This probably means your PyGTK installation is too old!')
    have_trayicon = False

from libpodcasts import podcastChannel
from libpodcasts import LocalDBReader
from libpodcasts import podcastItem
from libpodcasts import channels_to_model
from libpodcasts import update_channel_model_by_iter
from libpodcasts import load_channels
from libpodcasts import update_channels
from libpodcasts import save_channels
from libpodcasts import can_restore_from_opml
from libpodcasts import HTTPAuthError

from gpodder.libgpodder import gl

from libplayers import UserAppsReader

from libtagupdate import tagging_supported

if gpodder.interface == gpodder.GUI:
    WEB_BROWSER_ICON = 'web-browser'
elif gpodder.interface == gpodder.MAEMO:
    import hildon
    WEB_BROWSER_ICON = 'qgn_toolb_browser_web'

app_name = "gpodder"
app_version = "unknown" # will be set in main() call
app_authors = [
    _('Current maintainer:'), 'Thomas Perl <thpinfo.com>',
    '',
    _('Patches, bug reports and donations by:'), 'Adrien Beaucreux',
    'Alain Tauch', 'Alistair Sutton', 'Anders Kvist', 'Andrei Dolganov', 'Andrew Bennett', 'Andy Busch',
    'Antonio Roversi', 'Aravind Seshadri', 'Atte André Jensen', 'audioworld', 
    'Bastian Staeck', 'Bernd Schlapsi', 'Bill Barnard', 'Bill Peters', 'Bjørn Rasmussen', 'Camille Moncelier',
    'Carlos Moffat', 'Chris Arnold', 'Clark Burbidge', 'Cory Albrecht', 'daggpod', 'Daniel Ramos',
    'David Spreen', 'Doug Hellmann', 'Edouard Pellerin', 'FFranci72', 'Florian Richter', 'Frank Harper',
    'Franz Seidl', 'FriedBunny', 'Gerrit Sangel', 'Gilles Lehoux', 'Götz Waschk',
    'Haim Roitgrund', 'Heinz Erhard', 'Hex', 'Holger Bauer', 'Holger Leskien', 'Jens Thiele',
    'Jérôme Chabod', 'Jerry Moss',
    'Jessica Henline', 'João Trindade', 'Joel Calado', 'John Ferguson', 
    'José Luis Fustel', 'Joseph Bleau', 'Julio Acuña', 'Junio C Hamano',
    'Jürgen Schinker', 'Justin Forest',
    'Konstantin Ryabitsev', 'Leonid Ponomarev', 'Marcos Hernández', 'Mark Alford', 'Markus Golser', 'Mehmet Nur Olcay', 'Michael Salim',
    'Mika Leppinen', 'Mike Coulson', 'Mikolaj Laczynski', 'Mykola Nikishov', 'narf',
    'Nick L.', 'Nicolas Quienot', 'Ondrej Vesely', 
    'Ortwin Forster', 'Paul Elliot', 'Paul Rudkin',
    'Pavel Mlčoch', 'Peter Hoffmann', 'PhilF', 'Philippe Gouaillier', 'Pieter de Decker',
    'Preben Randhol', 'Rafael Proença', 'red26wings', 'Richard Voigt', 
    'Robert Young', 'Roel Groeneveld',
    'Scott Wegner', 'Sebastian Krause', 'Seth Remington', 'Shane Donohoe', 'Silvio Sisto', 'SPGoetze',
    'Stefan Lohmaier', 'Stephan Buys', 'Steve McCarthy', 'Stylianos Papanastasiou', 'Teo Ramirez',
    'Thomas Matthijs', 'Thomas Mills Hinkle', 'Thomas Nilsson', 
    'Tim Michelsen', 'Tim Preetz', 'Todd Zullinger', 'Tomas Matheson', 'Ville-Pekka Vainio', 'Vitaliy Bondar', 'VladDrac',
    'Vladimir Zemlyakov', 'Wilfred van Rooijen',
    '',
    'List may be incomplete - please contact me.'
]
app_copyright = '© 2005-2008 Thomas Perl and the gPodder Team'
app_website = 'http://www.gpodder.org/'

# these will be filled with pathnames in bin/gpodder
glade_dir = [ 'share', 'gpodder' ]
icon_dir = [ 'share', 'pixmaps', 'gpodder.png' ]
scalable_dir = [ 'share', 'icons', 'hicolor', 'scalable', 'apps', 'gpodder.svg' ]


class GladeWidget(SimpleGladeApp.SimpleGladeApp):
    gpodder_main_window = None
    finger_friendly_widgets = []

    def __init__( self, **kwargs):
        path = os.path.join( glade_dir, '%s.glade' % app_name)
        root = self.__class__.__name__
        domain = app_name

        SimpleGladeApp.SimpleGladeApp.__init__( self, path, root, domain, **kwargs)

        # Set widgets to finger-friendly mode if on Maemo
        for widget_name in self.finger_friendly_widgets:
            if hasattr(self, widget_name):
                self.set_finger_friendly(getattr(self, widget_name))
            else:
                log('Finger-friendly widget not found: %s', widget_name, sender=self)

        if root == 'gPodder':
            GladeWidget.gpodder_main_window = self.gPodder
        else:
            # If we have a child window, set it transient for our main window
            getattr( self, root).set_transient_for( GladeWidget.gpodder_main_window)

            if gpodder.interface == gpodder.GUI:
                if hasattr( self, 'center_on_widget'):
                    ( x, y ) = self.gpodder_main_window.get_position()
                    a = self.center_on_widget.allocation
                    ( x, y ) = ( x + a.x, y + a.y )
                    ( w, h ) = ( a.width, a.height )
                    ( pw, ph ) = getattr( self, root).get_size()
                    getattr( self, root).move( x + w/2 - pw/2, y + h/2 - ph/2)
                else:
                    getattr( self, root).set_position( gtk.WIN_POS_CENTER_ON_PARENT)

    def notification(self, message, title=None):
        util.idle_add(self.show_message, message, title)

    def show_message( self, message, title = None):
        if hasattr(self, 'tray_icon') and hasattr(self, 'minimized') and self.tray_icon and self.minimized:
            if title is None:
                title = 'gPodder'
            self.tray_icon.send_notification(message, title)            
            return
        
        if gpodder.interface == gpodder.GUI:
            dlg = gtk.MessageDialog(GladeWidget.gpodder_main_window, gtk.DIALOG_MODAL, gtk.MESSAGE_INFO, gtk.BUTTONS_OK)
            if title:
                dlg.set_title(str(title))
                dlg.set_markup('<span weight="bold" size="larger">%s</span>\n\n%s' % (title, message))
            else:
                dlg.set_markup('<span weight="bold" size="larger">%s</span>' % (message))
        elif gpodder.interface == gpodder.MAEMO:
            dlg = hildon.Note('information', (GladeWidget.gpodder_main_window, message))
        
        dlg.run()
        dlg.destroy()

    def set_finger_friendly(self, widget):
        """
        If we are on Maemo, we carry out the necessary
        operations to turn a widget into a finger-friendly
        one, depending on which type of widget it is (i.e.
        buttons will have more padding, TreeViews a thick
        scrollbar, etc..)
        """
        if gpodder.interface == gpodder.MAEMO:
            if isinstance(widget, gtk.Misc):
                widget.set_padding(0, 5)
            elif isinstance(widget, gtk.Button):
                for child in widget.get_children():
                    if isinstance(child, gtk.Alignment):
                        child.set_padding(5, 5, 5, 5)
                    else:
                        child.set_padding(5, 5)
            elif isinstance(widget, gtk.TreeView) or isinstance(widget, gtk.TextView):
                parent = widget.get_parent()
                if isinstance(parent, gtk.ScrolledWindow):
                    hildon.hildon_helper_set_thumb_scrollbar(parent, True)
            elif isinstance(widget, gtk.MenuItem):
                for child in widget.get_children():
                    self.set_finger_friendly(child)
                submenu = widget.get_submenu()
                if submenu is not None:
                    for child in submenu.get_children():
                        self.set_finger_friendly(child)
            elif isinstance(widget, gtk.Menu):
                for child in widget.get_children():
                    self.set_finger_friendly(child)
            else:
                log('Cannot set widget finger-friendly: %s', widget, sender=self)
                
        return widget

    def show_confirmation( self, message, title = None):
        if gpodder.interface == gpodder.GUI:
            affirmative = gtk.RESPONSE_YES
            dlg = gtk.MessageDialog(GladeWidget.gpodder_main_window, gtk.DIALOG_MODAL, gtk.MESSAGE_QUESTION, gtk.BUTTONS_YES_NO)
            if title:
                dlg.set_title(str(title))
                dlg.set_markup('<span weight="bold" size="larger">%s</span>\n\n%s' % (title, message))
            else:
                dlg.set_markup('<span weight="bold" size="larger">%s</span>' % (message))
        elif gpodder.interface == gpodder.MAEMO:
            affirmative = gtk.RESPONSE_OK
            dlg = hildon.Note('confirmation', (GladeWidget.gpodder_main_window, message))

        response = dlg.run()
        dlg.destroy()
        
        return response == affirmative

    def UsernamePasswordDialog( self, title, message, username=None, password=None, username_prompt=_('Username'), register_callback=None):
        """ An authentication dialog based on
                http://ardoris.wordpress.com/2008/07/05/pygtk-text-entry-dialog/ """

        dialog = gtk.MessageDialog(
            GladeWidget.gpodder_main_window,
            gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
            gtk.MESSAGE_QUESTION,
            gtk.BUTTONS_OK_CANCEL )

        dialog.set_image(gtk.image_new_from_stock(gtk.STOCK_DIALOG_AUTHENTICATION, gtk.ICON_SIZE_DIALOG))

        dialog.set_markup('<span weight="bold" size="larger">' + title + '</span>')
        dialog.set_title(_('Authentication required'))
        dialog.format_secondary_markup(message)
        dialog.set_default_response(gtk.RESPONSE_OK)

        if register_callback is not None:
            dialog.add_button(_('New user'), gtk.RESPONSE_HELP)

        username_entry = gtk.Entry()
        password_entry = gtk.Entry()

        username_entry.connect('activate', lambda w: password_entry.grab_focus())
        password_entry.set_visibility(False)
        password_entry.set_activates_default(True)

        if username is not None:
            username_entry.set_text(username)
        if password is not None:
            password_entry.set_text(password)

        table = gtk.Table(2, 2)
        table.set_row_spacings(6)
        table.set_col_spacings(6)

        username_label = gtk.Label()
        username_label.set_markup('<b>' + username_prompt + ':</b>')
        username_label.set_alignment(0.0, 0.5)
        table.attach(username_label, 0, 1, 0, 1, gtk.FILL, 0)
        table.attach(username_entry, 1, 2, 0, 1)

        password_label = gtk.Label()
        password_label.set_markup('<b>' + _('Password') + ':</b>')
        password_label.set_alignment(0.0, 0.5)
        table.attach(password_label, 0, 1, 1, 2, gtk.FILL, 0)
        table.attach(password_entry, 1, 2, 1, 2)

        dialog.vbox.pack_end(table, True, True, 0)
        dialog.show_all()
        response = dialog.run()

        while response == gtk.RESPONSE_HELP:
            register_callback()
            response = dialog.run()

        password_entry.set_visibility(True)
        dialog.destroy()

        return response == gtk.RESPONSE_OK, ( username_entry.get_text(), password_entry.get_text() )

    def show_copy_dialog( self, src_filename, dst_filename = None, dst_directory = None, title = _('Select destination')):
        if dst_filename is None:
            dst_filename = src_filename

        if dst_directory is None:
            dst_directory = os.path.expanduser( '~')

        ( base, extension ) = os.path.splitext( src_filename)

        if not dst_filename.endswith( extension):
            dst_filename += extension

        if gpodder.interface == gpodder.GUI:
            dlg = gtk.FileChooserDialog(title=title, parent=GladeWidget.gpodder_main_window, action=gtk.FILE_CHOOSER_ACTION_SAVE)
            dlg.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
            dlg.add_button(gtk.STOCK_SAVE, gtk.RESPONSE_OK)
        elif gpodder.interface == gpodder.MAEMO:
            dlg = hildon.FileChooserDialog(GladeWidget.gpodder_main_window, gtk.FILE_CHOOSER_ACTION_SAVE)

        dlg.set_do_overwrite_confirmation( True)
        dlg.set_current_name( os.path.basename( dst_filename))
        dlg.set_current_folder( dst_directory)

        result = False
        folder = dst_directory
        if dlg.run() == gtk.RESPONSE_OK:
            result = True
            dst_filename = dlg.get_filename()
            folder = dlg.get_current_folder()
            if not dst_filename.endswith( extension):
                dst_filename += extension

            log( 'Copying %s => %s', src_filename, dst_filename, sender = self)

            try:
                shutil.copyfile( src_filename, dst_filename)
            except:
                log( 'Error copying file.', sender = self, traceback = True)

        dlg.destroy()
        return (result, folder)


class gPodder(GladeWidget):
    finger_friendly_widgets = ['btnCancelFeedUpdate', 'label2', 'labelDownloads', 'itemQuit', 'menuPodcasts', 'advanced1', 'menuChannels', 'menuHelp']
    ENTER_URL_TEXT = _('Enter podcast URL...')
    
    def new(self):
        if gpodder.interface == gpodder.MAEMO:
            # Maemo-specific changes to the UI
            global scalable_dir
            scalable_dir = scalable_dir.replace('.svg', '.png')
            
            self.app = hildon.Program()
            gtk.set_application_name('gPodder')
            self.window = hildon.Window()
            self.window.connect('delete-event', self.on_gPodder_delete_event)
            self.window.connect('window-state-event', self.window_state_event)
    
            self.itemUpdateChannel.show()
            self.UpdateChannelSeparator.show()
            
            # Give toolbar to the hildon window
            self.toolbar.parent.remove(self.toolbar)
            self.window.add_toolbar(self.toolbar)

            # START TEMPORARY FIX FOR TOOLBAR STYLE
            # It seems like libglade for python still mixes
            # old GtkToolbar API with new ones - maybe this
            # is the reason why setting the style doesn't
            # work very well. This small hack fixes that :)
            self.toolbar.set_style(gtk.TOOLBAR_BOTH_HORIZ)
            def remove_label(w):
                if hasattr(w, 'set_label'):
                    w.set_label(None)
            self.toolbar.foreach(remove_label)
            # END TEMPORARY FIX FOR TOOLBAR STYLE
         
            self.app.add_window(self.window)
            self.vMain.reparent(self.window)
            self.gPodder = self.window
            
            # Reparent the main menu
            menu = gtk.Menu()
            for child in self.mainMenu.get_children():
                child.reparent(menu)
            self.itemQuit.reparent(menu)
            self.window.set_menu(menu)
         
            self.mainMenu.destroy()
            self.window.show()
            
            # do some widget hiding
            self.toolbar.remove(self.toolTransfer)
            self.itemTransferSelected.hide_all()
            self.item_email_subscriptions.hide_all()

            # Feed cache update button
            self.label120.set_text(_('Update'))
            
            # get screen real estate
            self.hboxContainer.set_border_width(0)

        self.gPodder.connect('key-press-event', self.on_key_press)
        self.treeChannels.connect('size-allocate', self.on_tree_channels_resize)

        if gl.config.show_url_entry_in_podcast_list:
            self.hboxAddChannel.show()

        if not gl.config.show_toolbar:
            self.toolbar.hide()

        gl.config.add_observer(self.on_config_changed)
        self.default_entry_text_color = self.entryAddChannel.get_style().text[gtk.STATE_NORMAL]
        self.entryAddChannel.connect('focus-in-event', self.entry_add_channel_focus)
        self.entryAddChannel.connect('focus-out-event', self.entry_add_channel_unfocus)
        self.entry_add_channel_unfocus(self.entryAddChannel, None)
        
        self.uar = None
        self.tray_icon = None

        self.fullscreen = False
        self.minimized = False
        self.gPodder.connect('window-state-event', self.window_state_event)
        
        self.already_notified_new_episodes = []
        self.show_hide_tray_icon()
        self.no_episode_selected.set_sensitive(False)

        self.itemShowToolbar.set_active(gl.config.show_toolbar)
        self.itemShowDescription.set_active(gl.config.episode_list_descriptions)
                   
        gl.config.connect_gtk_window(self.gPodder, 'main_window')
        gl.config.connect_gtk_paned( 'paned_position', self.channelPaned)

        gl.config.connect_gtk_spinbutton('max_downloads', self.spinMaxDownloads)
        gl.config.connect_gtk_togglebutton('max_downloads_enabled', self.cbMaxDownloads)
        gl.config.connect_gtk_spinbutton('limit_rate_value', self.spinLimitDownloads)
        gl.config.connect_gtk_togglebutton('limit_rate', self.cbLimitDownloads)

        # Make sure we free/close the download queue when we
        # update the "max downloads" spin button
        changed_cb = lambda spinbutton: services.download_status_manager.update_max_downloads()
        self.spinMaxDownloads.connect('value-changed', changed_cb)

        self.default_title = None
        if app_version.rfind('git') != -1:
            self.set_title('gPodder %s' % app_version)
        else:
            title = self.gPodder.get_title()
            if title is not None:
                self.set_title(title)
            else:
                self.set_title(_('gPodder'))

        gtk.about_dialog_set_url_hook(lambda dlg, link, data: util.open_website(link), None)

        # cell renderers for channel tree
        iconcolumn = gtk.TreeViewColumn('')

        iconcell = gtk.CellRendererPixbuf()
        iconcolumn.pack_start( iconcell, False)
        iconcolumn.add_attribute( iconcell, 'pixbuf', 5)
        self.cell_channel_icon = iconcell

        namecolumn = gtk.TreeViewColumn('')
        namecell = gtk.CellRendererText()
        namecell.set_property('foreground-set', True)
        namecell.set_property('ellipsize', pango.ELLIPSIZE_END)
        namecolumn.pack_start( namecell, True)
        namecolumn.add_attribute( namecell, 'markup', 2)
        namecolumn.add_attribute( namecell, 'foreground', 8)

        iconcell = gtk.CellRendererPixbuf()
        iconcell.set_property('xalign', 1.0)
        namecolumn.pack_start( iconcell, False)
        namecolumn.add_attribute( iconcell, 'pixbuf', 3)
        namecolumn.add_attribute(iconcell, 'visible', 7)
        self.cell_channel_pill = iconcell

        self.treeChannels.append_column(iconcolumn)
        self.treeChannels.append_column(namecolumn)
        self.treeChannels.set_headers_visible(False)

        # enable alternating colors hint
        self.treeAvailable.set_rules_hint( True)
        self.treeChannels.set_rules_hint( True)

        # connect to tooltip signals
        try:
            self.treeChannels.set_property('has-tooltip', True)
            self.treeChannels.connect('query-tooltip', self.treeview_channels_query_tooltip)
            self.treeAvailable.set_property('has-tooltip', True)
            self.treeAvailable.connect('query-tooltip', self.treeview_episodes_query_tooltip)
        except:
            log('I cannot set has-tooltip/query-tooltip (need at least PyGTK 2.12)', sender = self)
        self.last_tooltip_channel = None
        self.last_tooltip_episode = None
        self.podcast_list_can_tooltip = True
        self.episode_list_can_tooltip = True

        # Add our context menu to treeAvailable
        if gpodder.interface == gpodder.MAEMO:
            self.treeAvailable.connect('button-release-event', self.treeview_button_pressed)
        else:
            self.treeAvailable.connect('button-press-event', self.treeview_button_pressed)
        self.treeChannels.connect('button-press-event', self.treeview_channels_button_pressed)

        iconcell = gtk.CellRendererPixbuf()
        if gpodder.interface == gpodder.MAEMO:
            status_column_label = ''
        else:
            status_column_label = _('Status')
        iconcolumn = gtk.TreeViewColumn(status_column_label, iconcell, pixbuf=4)

        namecell = gtk.CellRendererText()
        namecell.set_property('ellipsize', pango.ELLIPSIZE_END)
        namecolumn = gtk.TreeViewColumn(_("Episode"), namecell, markup=6)
        namecolumn.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        namecolumn.set_expand(True)

        sizecell = gtk.CellRendererText()
        sizecolumn = gtk.TreeViewColumn( _("Size"), sizecell, text=2)

        releasecell = gtk.CellRendererText()
        releasecolumn = gtk.TreeViewColumn( _("Released"), releasecell, text=5)
        
        for itemcolumn in (iconcolumn, namecolumn, sizecolumn, releasecolumn):
            itemcolumn.set_reorderable(True)
            self.treeAvailable.append_column(itemcolumn)

        if gpodder.interface == gpodder.MAEMO:
            # Due to screen space contraints, we
            # hide these columns here by default
            self.column_size = sizecolumn
            self.column_released = releasecolumn
            self.column_released.set_visible(False)
            self.column_size.set_visible(False)

        # enable search in treeavailable
        self.treeAvailable.set_search_equal_func( self.treeAvailable_search_equal)

        # enable multiple selection support
        self.treeAvailable.get_selection().set_mode( gtk.SELECTION_MULTIPLE)
        self.treeDownloads.get_selection().set_mode( gtk.SELECTION_MULTIPLE)
        
        # columns and renderers for "download progress" tab
        episodecell = gtk.CellRendererText()
        episodecell.set_property('ellipsize', pango.ELLIPSIZE_END)
        episodecolumn = gtk.TreeViewColumn( _("Episode"), episodecell, text=0)
        episodecolumn.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        episodecolumn.set_expand(True)
        
        speedcell = gtk.CellRendererText()
        speedcolumn = gtk.TreeViewColumn( _("Speed"), speedcell, text=1)
        
        progresscell = gtk.CellRendererProgress()
        progresscolumn = gtk.TreeViewColumn( _("Progress"), progresscell, value=2)
        progresscolumn.set_expand(True)
        
        for itemcolumn in ( episodecolumn, speedcolumn, progresscolumn ):
            self.treeDownloads.append_column( itemcolumn)

        # After we've set up most of the window, show it :)
        if not gpodder.interface == gpodder.MAEMO:
            self.gPodder.show()

        if self.tray_icon:
            if gl.config.start_iconified: 
                self.iconify_main_window()
            elif gl.config.minimize_to_tray:
                self.tray_icon.set_visible(False)

        services.download_status_manager.register( 'list-changed', self.download_status_updated)
        services.download_status_manager.register( 'progress-changed', self.download_progress_updated)
        services.cover_downloader.register('cover-available', self.cover_download_finished)
        services.cover_downloader.register('cover-removed', self.cover_file_removed)
        self.cover_cache = {}

        self.treeDownloads.set_model( services.download_status_manager.tree_model)
        
        #Add Drag and Drop Support
        flags = gtk.DEST_DEFAULT_ALL
        targets = [ ('text/plain', 0, 2), ('STRING', 0, 3), ('TEXT', 0, 4) ]
        actions = gtk.gdk.ACTION_DEFAULT | gtk.gdk.ACTION_COPY
        self.treeChannels.drag_dest_set( flags, targets, actions)
        self.treeChannels.connect( 'drag_data_received', self.drag_data_received)

        # Subscribed channels
        self.active_channel = None
        self.channels = load_channels()
        self.update_podcasts_tab()

        # load list of user applications for audio playback
        self.user_apps_reader = UserAppsReader(['audio', 'video'])
        Thread(target=self.read_apps).start()

        # Clean up old, orphaned download files
        gl.clean_up_downloads( delete_partial = True)

        # Set the "Device" menu item for the first time
        self.update_item_device()

        # Last folder used for saving episodes
        self.folder_for_saving_episodes = None

        # Set up default channel colors
        self.channel_colors = {
            'default': None,
            'updating': gl.config.color_updating_feeds,
            'parse_error': '#ff0000',
            }

        # Now, update the feed cache, when everything's in place
        self.btnUpdateFeeds.show_all()
        self.updated_feeds = 0
        self.updating_feed_cache = False
        self.feed_cache_update_cancelled = False
        self.update_feed_cache(force_update=gl.config.update_on_startup)

        # Start the auto-update procedure
        self.auto_update_procedure(first_run=True)

        # Delete old episodes if the user wishes to
        if gl.config.auto_remove_old_episodes:
            old_episodes = self.get_old_episodes()
            if len(old_episodes) > 0:
                self.delete_episode_list(old_episodes, confirm=False)
                self.updateComboBox()

        # First-time users should be asked if they want to see the OPML
        if len(self.channels) == 0:
            util.idle_add(self.on_itemUpdate_activate, None)

    def on_tree_channels_resize(self, widget, allocation):
        if not gl.config.podcast_sidebar_save_space:
            return

        window_allocation = self.gPodder.get_allocation()
        percentage = 100. * float(allocation.width) / float(window_allocation.width)
        if hasattr(self, 'cell_channel_icon'):
            self.cell_channel_icon.set_property('visible', bool(percentage > 22.))
        if hasattr(self, 'cell_channel_pill'):
            self.cell_channel_pill.set_property('visible', bool(percentage > 25.))

    def entry_add_channel_focus(self, widget, event):
        widget.modify_text(gtk.STATE_NORMAL, self.default_entry_text_color)
        if widget.get_text() == self.ENTER_URL_TEXT:
            widget.set_text('')

    def entry_add_channel_unfocus(self, widget, event):
        if widget.get_text() == '':
            widget.set_text(self.ENTER_URL_TEXT)
            widget.modify_text(gtk.STATE_NORMAL, gtk.gdk.color_parse('#aaaaaa'))

    def on_config_changed(self, name, old_value, new_value):
        if name == 'show_toolbar':
            if new_value:
                self.toolbar.show()
            else:
                self.toolbar.hide()
        elif name == 'episode_list_descriptions':
            self.updateTreeView()
        elif name == 'show_url_entry_in_podcast_list':
            if new_value:
                self.hboxAddChannel.show()
            else:
                self.hboxAddChannel.hide()

    def read_apps(self):
        time.sleep(3) # give other parts of gpodder a chance to start up
        self.user_apps_reader.read()
        util.idle_add(self.user_apps_reader.get_applications_as_model, 'audio', False)
        util.idle_add(self.user_apps_reader.get_applications_as_model, 'video', False)

    def treeview_episodes_query_tooltip(self, treeview, x, y, keyboard_tooltip, tooltip):
        # With get_bin_window, we get the window that contains the rows without
        # the header. The Y coordinate of this window will be the height of the
        # treeview header. This is the amount we have to subtract from the
        # event's Y coordinate to get the coordinate to pass to get_path_at_pos
        (x_bin, y_bin) = treeview.get_bin_window().get_position()
        y -= x_bin
        y -= y_bin
        (path, column, rx, ry) = treeview.get_path_at_pos( x, y) or (None,)*4

        if not self.episode_list_can_tooltip or (column is not None and column != treeview.get_columns()[0]):
            self.last_tooltip_episode = None
            return False

        if path is not None:
            model = treeview.get_model()
            iter = model.get_iter(path)
            url = model.get_value(iter, 0)
            description = model.get_value(iter, 7)
            if self.last_tooltip_episode is not None and self.last_tooltip_episode != url:
                self.last_tooltip_episode = None
                return False
            self.last_tooltip_episode = url

            if len(description) > 400:
                description = description[:398]+'[...]'

            tooltip.set_text(description)
            return True

        self.last_tooltip_episode = None
        return False

    def podcast_list_allow_tooltips(self):
        self.podcast_list_can_tooltip = True

    def episode_list_allow_tooltips(self):
        self.episode_list_can_tooltip = True

    def treeview_channels_query_tooltip(self, treeview, x, y, keyboard_tooltip, tooltip):
        (path, column, rx, ry) = treeview.get_path_at_pos( x, y) or (None,)*4

        if not self.podcast_list_can_tooltip or (column is not None and column != treeview.get_columns()[0]):
            self.last_tooltip_channel = None
            return False

        if path is not None:
            model = treeview.get_model()
            iter = model.get_iter(path)
            url = model.get_value(iter, 0)
            for channel in self.channels:
                if channel.url == url:
                    if self.last_tooltip_channel is not None and self.last_tooltip_channel != channel:
                        self.last_tooltip_channel = None
                        return False
                    self.last_tooltip_channel = channel
                    channel.request_save_dir_size()
                    diskspace_str = gl.format_filesize(channel.save_dir_size, 0)
                    error_str = model.get_value(iter, 6)
                    if error_str:
                        error_str = _('Feedparser error: %s') % saxutils.escape(error_str.strip())
                        error_str = '<span foreground="#ff0000">%s</span>' % error_str
                    table = gtk.Table(rows=3, columns=3)
                    table.set_row_spacings(5)
                    table.set_col_spacings(5)
                    table.set_border_width(5)

                    heading = gtk.Label()
                    heading.set_alignment(0, 1)
                    heading.set_markup('<b><big>%s</big></b>\n<small>%s</small>' % (saxutils.escape(channel.title), saxutils.escape(channel.url)))
                    table.attach(heading, 0, 1, 0, 1)
                    size_info = gtk.Label()
                    size_info.set_alignment(1, 1)
                    size_info.set_justify(gtk.JUSTIFY_RIGHT)
                    size_info.set_markup('<b>%s</b>\n<small>%s</small>' % (diskspace_str, _('disk usage')))
                    table.attach(size_info, 2, 3, 0, 1)

                    table.attach(gtk.HSeparator(), 0, 3, 1, 2)

                    if len(channel.description) < 500:
                        description = channel.description
                    else:
                        pos = channel.description.find('\n\n')
                        if pos == -1 or pos > 500:
                            description = channel.description[:498]+'[...]'
                        else:
                            description = channel.description[:pos]

                    description = gtk.Label(description)
                    if error_str:
                        description.set_markup(error_str)
                    description.set_alignment(0, 0)
                    description.set_line_wrap(True)
                    table.attach(description, 0, 3, 2, 3)

                    table.show_all()
                    tooltip.set_custom(table)

                    return True

        self.last_tooltip_channel = None
        return False

    def update_m3u_playlist_clicked(self, widget):
        self.active_channel.update_m3u_playlist()
        self.show_message(_('Updated M3U playlist in download folder.'), _('Updated playlist'))

    def treeview_channels_button_pressed( self, treeview, event):
        global WEB_BROWSER_ICON

        if event.button == 3:
            ( x, y ) = ( int(event.x), int(event.y) )
            ( path, column, rx, ry ) = treeview.get_path_at_pos( x, y) or (None,)*4

            paths = []

            # Did the user right-click into a selection?
            selection = treeview.get_selection()
            if selection.count_selected_rows() and path:
                ( model, paths ) = selection.get_selected_rows()
                if path not in paths:
                    # We have right-clicked, but not into the 
                    # selection, assume we don't want to operate
                    # on the selection
                    paths = []

            # No selection or right click not in selection:
            # Select the single item where we clicked
            if not len( paths) and path:
                treeview.grab_focus()
                treeview.set_cursor( path, column, 0)

                ( model, paths ) = ( treeview.get_model(), [ path ] )

            # We did not find a selection, and the user didn't
            # click on an item to select -- don't show the menu
            if not len( paths):
                return True

            menu = gtk.Menu()

            item = gtk.ImageMenuItem( _('Open download folder'))
            item.set_image( gtk.image_new_from_icon_name( 'folder-open', gtk.ICON_SIZE_MENU))
            item.connect('activate', lambda x: util.gui_open(self.active_channel.save_dir))
            menu.append( item)

            item = gtk.ImageMenuItem( _('Update Feed'))
            item.set_image( gtk.image_new_from_icon_name( 'gtk-refresh', gtk.ICON_SIZE_MENU))
            item.connect('activate', self.on_itemUpdateChannel_activate )
            item.set_sensitive( not self.updating_feed_cache )
            menu.append( item)

            if gl.config.create_m3u_playlists:
                item = gtk.ImageMenuItem(_('Update M3U playlist'))
                item.set_image(gtk.image_new_from_stock(gtk.STOCK_REFRESH, gtk.ICON_SIZE_MENU))
                item.connect('activate', self.update_m3u_playlist_clicked)
                menu.append(item)

            if self.active_channel.link:
                item = gtk.ImageMenuItem(_('Visit website'))
                item.set_image(gtk.image_new_from_icon_name(WEB_BROWSER_ICON, gtk.ICON_SIZE_MENU))
                item.connect('activate', lambda w: util.open_website(self.active_channel.link))
                menu.append(item)

            if self.active_channel.channel_is_locked:
                item = gtk.ImageMenuItem(_('Allow deletion of all episodes'))
                item.set_image(gtk.image_new_from_stock(gtk.STOCK_DIALOG_AUTHENTICATION, gtk.ICON_SIZE_MENU))
                item.connect('activate', self.on_channel_toggle_lock_activate)
                menu.append(self.set_finger_friendly(item))
            else:
                item = gtk.ImageMenuItem(_('Prohibit deletion of all episodes'))
                item.set_image(gtk.image_new_from_stock(gtk.STOCK_DIALOG_AUTHENTICATION, gtk.ICON_SIZE_MENU))
                item.connect('activate', self.on_channel_toggle_lock_activate)
                menu.append(self.set_finger_friendly(item))


            menu.append( gtk.SeparatorMenuItem())

            item = gtk.ImageMenuItem(gtk.STOCK_EDIT)
            item.connect( 'activate', self.on_itemEditChannel_activate)
            menu.append( item)

            item = gtk.ImageMenuItem(gtk.STOCK_DELETE)
            item.connect( 'activate', self.on_itemRemoveChannel_activate)
            menu.append( item)

            menu.show_all()
            # Disable tooltips while we are showing the menu, so 
            # the tooltip will not appear over the menu
            self.podcast_list_can_tooltip = False
            menu.connect('deactivate', lambda menushell: self.podcast_list_allow_tooltips())
            menu.popup( None, None, None, event.button, event.time)

            return True

    def on_itemClose_activate(self, widget):
        if self.tray_icon is not None:
            if gpodder.interface == gpodder.MAEMO:
                self.gPodder.set_property('visible', False)
            else:
                self.iconify_main_window()
        else:
            self.on_gPodder_delete_event(widget)

    def cover_file_removed(self, channel_url):
        """
        The Cover Downloader calls this when a previously-
        available cover has been removed from the disk. We
        have to update our cache to reflect this change.
        """
        (COLUMN_URL, COLUMN_PIXBUF) = (0, 5)
        for row in self.treeChannels.get_model():
            if row[COLUMN_URL] == channel_url:
                row[COLUMN_PIXBUF] = None
                key = (channel_url, gl.config.podcast_list_icon_size, \
                        gl.config.podcast_list_icon_size)
                if key in self.cover_cache:
                    del self.cover_cache[key]
        
    
    def cover_download_finished(self, channel_url, pixbuf):
        """
        The Cover Downloader calls this when it has finished
        downloading (or registering, if already downloaded)
        a new channel cover, which is ready for displaying.
        """
        if pixbuf is not None:
            (COLUMN_URL, COLUMN_PIXBUF) = (0, 5)
            for row in self.treeChannels.get_model():
                if row[COLUMN_URL] == channel_url and row[COLUMN_PIXBUF] is None:
                    new_pixbuf = util.resize_pixbuf_keep_ratio(pixbuf, gl.config.podcast_list_icon_size, gl.config.podcast_list_icon_size, channel_url, self.cover_cache)
                    row[COLUMN_PIXBUF] = new_pixbuf or pixbuf

    def save_episode_as_file( self, url, *args):
        episode = self.active_channel.find_episode(url)

        folder = self.folder_for_saving_episodes
        (result, folder) = self.show_copy_dialog(src_filename=episode.local_filename(), dst_filename=episode.sync_filename(), dst_directory=folder)
        self.folder_for_saving_episodes = folder

    def copy_episode_bluetooth(self, url, *args):
        episode = self.active_channel.find_episode(url)
        filename = episode.local_filename()

        if gl.config.bluetooth_use_device_address:
            device = gl.config.bluetooth_device_address
        else:
            device = None

        destfile = os.path.join(gl.tempdir, util.sanitize_filename(episode.sync_filename()))
        (base, ext) = os.path.splitext(filename)
        if not destfile.endswith(ext):
            destfile += ext

        if gl.config.bluetooth_use_converter:
            title = _('Converting file')
            message = _('Please wait while gPodder converts your media file for bluetooth file transfer.')
            dlg = gtk.MessageDialog(self.gPodder, gtk.DIALOG_MODAL, gtk.MESSAGE_INFO, gtk.BUTTONS_NONE)
            dlg.set_title(title)
            dlg.set_markup('<span weight="bold" size="larger">%s</span>\n\n%s'%(title, message))
            dlg.show_all()
        else:
            dlg = None

        def convert_and_send_thread(filename, destfile, device, dialog, notify):
            if gl.config.bluetooth_use_converter:
                p = subprocess.Popen([gl.config.bluetooth_converter, filename, destfile], stdout=sys.stdout, stderr=sys.stderr)
                result = p.wait()
                if dialog is not None:
                    dialog.destroy()
            else:
                try:
                    shutil.copyfile(filename, destfile)
                    result = 0
                except:
                    log('Cannot copy "%s" to "%s".', filename, destfile, sender=self)
                    result = 1

            if result == 0 or not os.path.exists(destfile):
                util.bluetooth_send_file(destfile, device)
            else:
                notify(_('Error converting file.'), _('Bluetooth file transfer'))
            util.delete_file(destfile)

        Thread(target=convert_and_send_thread, args=[filename, destfile, device, dlg, self.notification]).start()

    def treeview_button_pressed( self, treeview, event):
        global WEB_BROWSER_ICON

        # Use right-click for the Desktop version and left-click for Maemo
        if (event.button == 1 and gpodder.interface == gpodder.MAEMO) or \
           (event.button == 3 and gpodder.interface == gpodder.GUI):
            ( x, y ) = ( int(event.x), int(event.y) )
            ( path, column, rx, ry ) = treeview.get_path_at_pos( x, y) or (None,)*4

            paths = []

            # Did the user right-click into a selection?
            selection = self.treeAvailable.get_selection()
            if selection.count_selected_rows() and path:
                ( model, paths ) = selection.get_selected_rows()
                if path not in paths:
                    # We have right-clicked, but not into the 
                    # selection, assume we don't want to operate
                    # on the selection
                    paths = []

            # No selection or right click not in selection:
            # Select the single item where we clicked
            if not len( paths) and path:
                treeview.grab_focus()
                treeview.set_cursor( path, column, 0)

                ( model, paths ) = ( treeview.get_model(), [ path ] )

            # We did not find a selection, and the user didn't
            # click on an item to select -- don't show the menu
            if not len( paths):
                return True

            first_url = model.get_value( model.get_iter( paths[0]), 0)
            episode = db.load_episode(first_url)

            menu = gtk.Menu()

            (can_play, can_download, can_transfer, can_cancel, can_delete, open_instead_of_play) = self.play_or_download()

            if can_play:
                if open_instead_of_play:
                    item = gtk.ImageMenuItem(gtk.STOCK_OPEN)
                else:
                    item = gtk.ImageMenuItem(gtk.STOCK_MEDIA_PLAY)
                item.connect( 'activate', lambda w: self.on_treeAvailable_row_activated( self.toolPlay))
                menu.append(self.set_finger_friendly(item))
                
            if not episode['is_locked'] and can_delete:
                item = gtk.ImageMenuItem(gtk.STOCK_DELETE)
                item.connect('activate', self.on_btnDownloadedDelete_clicked)
                menu.append(self.set_finger_friendly(item))

            if can_cancel:
                item = gtk.ImageMenuItem( _('Cancel download'))
                item.set_image( gtk.image_new_from_stock( gtk.STOCK_STOP, gtk.ICON_SIZE_MENU))
                item.connect( 'activate', lambda w: self.on_treeDownloads_row_activated( self.toolCancel))
                menu.append(self.set_finger_friendly(item))

            if can_download:
                item = gtk.ImageMenuItem(_('Download'))
                item.set_image( gtk.image_new_from_stock( gtk.STOCK_GO_DOWN, gtk.ICON_SIZE_MENU))
                item.connect( 'activate', lambda w: self.on_treeAvailable_row_activated( self.toolDownload))
                menu.append(self.set_finger_friendly(item))
                
            if episode['state'] == db.STATE_NORMAL and not episode['is_played']: # can_download:
                item = gtk.ImageMenuItem(_('Do not download'))
                item.set_image(gtk.image_new_from_stock(gtk.STOCK_DELETE, gtk.ICON_SIZE_MENU))
                item.connect('activate', lambda w: self.mark_selected_episodes_old())
                menu.append(self.set_finger_friendly(item))
            elif episode['state'] == db.STATE_NORMAL and can_download:
                item = gtk.ImageMenuItem(_('Mark as new'))
                item.set_image(gtk.image_new_from_stock(gtk.STOCK_ABOUT, gtk.ICON_SIZE_MENU))
                item.connect('activate', lambda w: self.mark_selected_episodes_new())
                menu.append(self.set_finger_friendly(item))

            if can_play and not can_download:
                menu.append( gtk.SeparatorMenuItem())
                item = gtk.ImageMenuItem(_('Save to disk'))
                item.set_image(gtk.image_new_from_stock(gtk.STOCK_SAVE_AS, gtk.ICON_SIZE_MENU))
                item.connect( 'activate', lambda w: self.for_each_selected_episode_url(self.save_episode_as_file))
                menu.append(self.set_finger_friendly(item))
                if gl.bluetooth_available:
                    item = gtk.ImageMenuItem(_('Send via bluetooth'))
                    item.set_image(gtk.image_new_from_icon_name('bluetooth', gtk.ICON_SIZE_MENU))
                    item.connect('activate', lambda w: self.copy_episode_bluetooth(episode_url))
                    menu.append(self.set_finger_friendly(item))
                if can_transfer:
                    item = gtk.ImageMenuItem(_('Transfer to %s') % gl.get_device_name())
                    item.set_image(gtk.image_new_from_icon_name('multimedia-player', gtk.ICON_SIZE_MENU))
                    item.connect('activate', lambda w: self.on_treeAvailable_row_activated(self.toolTransfer))
                    menu.append(self.set_finger_friendly(item))

            if can_play:
                menu.append( gtk.SeparatorMenuItem())
                is_played = episode['is_played']
                if is_played:
                    item = gtk.ImageMenuItem(_('Mark as unplayed'))
                    item.set_image( gtk.image_new_from_stock( gtk.STOCK_CANCEL, gtk.ICON_SIZE_MENU))
                    item.connect( 'activate', lambda w: self.on_item_toggle_played_activate( w, False, False))
                    menu.append(self.set_finger_friendly(item))
                else:
                    item = gtk.ImageMenuItem(_('Mark as played'))
                    item.set_image( gtk.image_new_from_stock( gtk.STOCK_APPLY, gtk.ICON_SIZE_MENU))
                    item.connect( 'activate', lambda w: self.on_item_toggle_played_activate( w, False, True))
                    menu.append(self.set_finger_friendly(item))

                is_locked = episode['is_locked']
                if is_locked:
                    item = gtk.ImageMenuItem(_('Allow deletion'))
                    item.set_image(gtk.image_new_from_stock(gtk.STOCK_DIALOG_AUTHENTICATION, gtk.ICON_SIZE_MENU))
                    item.connect('activate', self.on_item_toggle_lock_activate)
                    menu.append(self.set_finger_friendly(item))
                else:
                    item = gtk.ImageMenuItem(_('Prohibit deletion'))
                    item.set_image(gtk.image_new_from_stock(gtk.STOCK_DIALOG_AUTHENTICATION, gtk.ICON_SIZE_MENU))
                    item.connect('activate', self.on_item_toggle_lock_activate)
                    menu.append(self.set_finger_friendly(item))

            if len(paths) == 1:
                menu.append(gtk.SeparatorMenuItem())
                # Single item, add episode information menu item
                episode_url = model.get_value( model.get_iter( paths[0]), 0)
                item = gtk.ImageMenuItem(_('Episode details'))
                item.set_image( gtk.image_new_from_stock( gtk.STOCK_INFO, gtk.ICON_SIZE_MENU))
                item.connect( 'activate', lambda w: self.on_treeAvailable_row_activated( self.treeAvailable))
                menu.append(self.set_finger_friendly(item))
                episode = self.active_channel.find_episode(episode_url)
                # If we have it, also add episode website link
                if episode and episode.link and episode.link != episode.url:
                    item = gtk.ImageMenuItem(_('Visit website'))
                    item.set_image(gtk.image_new_from_icon_name(WEB_BROWSER_ICON, gtk.ICON_SIZE_MENU))
                    item.connect('activate', lambda w: util.open_website(episode.link))
                    menu.append(self.set_finger_friendly(item))
            
            if gpodder.interface == gpodder.MAEMO:
                # Because we open the popup on left-click for Maemo,
                # we also include a non-action to close the menu
                menu.append(gtk.SeparatorMenuItem())
                item = gtk.ImageMenuItem(_('Close this menu'))
                item.set_image(gtk.image_new_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU))
                menu.append(self.set_finger_friendly(item))

            menu.show_all()
            # Disable tooltips while we are showing the menu, so 
            # the tooltip will not appear over the menu
            self.episode_list_can_tooltip = False
            menu.connect('deactivate', lambda menushell: self.episode_list_allow_tooltips())
            menu.popup( None, None, None, event.button, event.time)

            return True

    def set_title(self, new_title):
        self.default_title = new_title
        self.gPodder.set_title(new_title)

    def download_progress_updated( self, count, percentage):
        title = [ self.default_title ]

        total_speed = gl.format_filesize(services.download_status_manager.total_speed())

        if count == 1:
            title.append( _('downloading one file'))
        elif count > 1:
            title.append( _('downloading %d files') % count)

        if len(title) == 2:
            title[1] = ''.join( [ title[1], ' (%d%%, %s/s)' % (percentage, total_speed) ])

        self.gPodder.set_title( ' - '.join( title))

        # Have all the downloads completed?
        # If so execute user command if defined, else do nothing
        if count == 0:
            if len(gl.config.cmd_all_downloads_complete) > 0:
                Thread(target=gl.ext_command_thread, args=(self.notification,gl.config.cmd_all_downloads_complete)).start()
 
    def playback_episode(self, episode, stream=False):
        (success, application) = gl.playback_episode(episode, stream)
        if not success:
            self.show_message( _('The selected player application cannot be found. Please check your media player settings in the preferences dialog.'), _('Error opening player: %s') % ( saxutils.escape( application), ))
        self.updateComboBox(only_selected_channel=True)

    def treeAvailable_search_equal( self, model, column, key, iter, data = None):
        if model is None:
            return True

        key = key.lower()

        # columns, as defined in libpodcasts' get model method
        # 1 = episode title, 7 = description
        columns = (1, 7)

        for column in columns:
            value = model.get_value( iter, column).lower()
            if value.find( key) != -1:
                return False

        return True
    
    def change_menu_item(self, menuitem, icon=None, label=None):
        if icon is not None:
            menuitem.get_image().set_from_icon_name(icon, gtk.ICON_SIZE_MENU)
        if label is not None:
            label_widget = menuitem.get_child()
            label_widget.set_text(label)

    def play_or_download(self):
        if self.wNotebook.get_current_page() > 0:
            return

        ( can_play, can_download, can_transfer, can_cancel, can_delete ) = (False,)*5
        ( is_played, is_locked ) = (False,)*2

        open_instead_of_play = False

        selection = self.treeAvailable.get_selection()
        if selection.count_selected_rows() > 0:
            (model, paths) = selection.get_selected_rows()
         
            for path in paths:
                url = model.get_value( model.get_iter( path), 0)
                local_filename = model.get_value( model.get_iter( path), 8)

                episode = podcastItem.load(url, self.active_channel)

                if episode.file_type() not in ('audio', 'video'):
                    open_instead_of_play = True

                if episode.was_downloaded():
                    can_play = episode.was_downloaded(and_exists=True)
                    can_delete = True
                    is_played = episode.is_played
                    is_locked = episode.is_locked
                    if not can_play:
                        can_download = True
                else:
                    if services.download_status_manager.is_download_in_progress(url):
                        can_cancel = True
                    else:
                        can_download = True

        can_download = can_download and not can_cancel
        can_play = gl.config.enable_streaming or (can_play and not can_cancel and not can_download)
        can_transfer = can_play and gl.config.device_type != 'none' and not can_cancel and not can_download

        if open_instead_of_play:
            self.toolPlay.set_stock_id(gtk.STOCK_OPEN)
            can_transfer = False
        else:
            self.toolPlay.set_stock_id(gtk.STOCK_MEDIA_PLAY)

        self.toolPlay.set_sensitive( can_play)
        self.toolDownload.set_sensitive( can_download)
        self.toolTransfer.set_sensitive( can_transfer)
        self.toolCancel.set_sensitive( can_cancel)

        if can_cancel:
            self.item_cancel_download.show_all()
        else:
            self.item_cancel_download.hide_all()
        if can_download:
            self.itemDownloadSelected.show_all()
        else:
            self.itemDownloadSelected.hide_all()
        if can_play:
            if open_instead_of_play:
                self.itemOpenSelected.show_all()
                self.itemPlaySelected.hide_all()
            else:
                self.itemPlaySelected.show_all()
                self.itemOpenSelected.hide_all()
            if not can_download:
                self.itemDeleteSelected.show_all()
            else:
                self.itemDeleteSelected.hide_all()
            self.item_toggle_played.show_all()
            self.item_toggle_lock.show_all()
            self.separator9.show_all()
            if is_played:
                self.change_menu_item(self.item_toggle_played, gtk.STOCK_CANCEL, _('Mark as unplayed'))
            else:
                self.change_menu_item(self.item_toggle_played, gtk.STOCK_APPLY, _('Mark as played'))
            if is_locked:
                self.change_menu_item(self.item_toggle_lock, gtk.STOCK_DIALOG_AUTHENTICATION, _('Allow deletion'))
            else:
                self.change_menu_item(self.item_toggle_lock, gtk.STOCK_DIALOG_AUTHENTICATION, _('Prohibit deletion'))
        else:
            self.itemPlaySelected.hide_all()
            self.itemOpenSelected.hide_all()
            self.itemDeleteSelected.hide_all()
            self.item_toggle_played.hide_all()
            self.item_toggle_lock.hide_all()
            self.separator9.hide_all()
        if can_play or can_download or can_cancel:
            self.item_episode_details.show_all()
            self.separator16.show_all()
            self.no_episode_selected.hide_all()
        else:
            self.item_episode_details.hide_all()
            self.separator16.hide_all()
            self.no_episode_selected.show_all()

        return (can_play, can_download, can_transfer, can_cancel, can_delete, open_instead_of_play)

    def download_status_updated( self):
        count = services.download_status_manager.count()
        if count:
            self.labelDownloads.set_text( _('Downloads (%d)') % count)
        else:
            self.labelDownloads.set_text( _('Downloads'))

        self.updateComboBox()

    def on_cbMaxDownloads_toggled(self, widget, *args):
        self.spinMaxDownloads.set_sensitive(self.cbMaxDownloads.get_active())

    def on_cbLimitDownloads_toggled(self, widget, *args):
        self.spinLimitDownloads.set_sensitive(self.cbLimitDownloads.get_active())

    def episode_new_status_changed(self):
        self.updateComboBox()
        self.updateTreeView()

    def updateComboBox(self, selected_url=None, only_selected_channel=False):
        (model, iter) = self.treeChannels.get_selection().get_selected()

        if only_selected_channel:
            if iter and self.active_channel is not None:
                update_channel_model_by_iter( self.treeChannels.get_model(),
                    iter, self.active_channel, self.channel_colors,
                    self.cover_cache, *(gl.config.podcast_list_icon_size,)*2 )
        else:
            if model and iter and selected_url is None:
                # Get the URL of the currently-selected podcast
                selected_url = model.get_value(iter, 0)

            rect = self.treeChannels.get_visible_rect()
            self.treeChannels.set_model( channels_to_model( self.channels,
                self.channel_colors, self.cover_cache,
                *(gl.config.podcast_list_icon_size,)*2 ))
            util.idle_add(self.treeChannels.scroll_to_point, rect.x, rect.y)

            try:
                selected_path = (0,)
                # Find the previously-selected URL in the new
                # model if we have an URL (else select first)
                if selected_url is not None:
                    model = self.treeChannels.get_model()
                    pos = model.get_iter_first()
                    while pos is not None:
                        url = model.get_value(pos, 0)
                        if url == selected_url:
                            selected_path = model.get_path(pos)
                            break
                        pos = model.iter_next(pos)

                self.treeChannels.get_selection().select_path(selected_path)
            except:
                log( 'Cannot set selection on treeChannels', sender = self)
        self.on_treeChannels_cursor_changed( self.treeChannels)
    
    def updateTreeView(self, retain_position=True):
        if self.channels and self.active_channel is not None:
            rect = self.treeAvailable.get_visible_rect()
            self.treeAvailable.set_model(self.active_channel.tree_model)
            if retain_position:
                util.idle_add(self.treeAvailable.scroll_to_point, rect.x, rect.y)
            self.treeAvailable.columns_autosize()
            self.play_or_download()
        else:
            if self.treeAvailable.get_model():
                self.treeAvailable.get_model().clear()
    
    def drag_data_received(self, widget, context, x, y, sel, ttype, time):
        (path, column, rx, ry) = self.treeChannels.get_path_at_pos( x, y) or (None,)*4

        dnd_channel = None
        if path is not None:
            model = self.treeChannels.get_model()
            iter = model.get_iter(path)
            url = model.get_value(iter, 0)
            for channel in self.channels:
                if channel.url == url:
                    dnd_channel = channel
                    break

        result = sel.data
        rl = result.strip().lower()
        if (rl.endswith('.jpg') or rl.endswith('.png') or rl.endswith('.gif') or rl.endswith('.svg')) and dnd_channel is not None:
            services.cover_downloader.replace_cover(dnd_channel, result)
        else:
            self.add_new_channel(result)

    def add_new_channel(self, result=None, ask_download_new=True, quiet=False, block=False, authentication_tokens=None):
        (scheme, rest) = result.split('://', 1)
        result = util.normalize_feed_url(result)

        if not result:
            cute_scheme = saxutils.escape(scheme)+'://'
            title = _('%s URLs are not supported') % cute_scheme
            message = _('gPodder does not understand the URL you supplied.')
            self.show_message( message, title)
            return

        for old_channel in self.channels:
            if old_channel.url == result:
                log( 'Channel already exists: %s', result)
                # Select the existing channel in combo box
                for i in range( len( self.channels)):
                    if self.channels[i] == old_channel:
                        self.treeChannels.get_selection().select_path( (i,))
                        self.on_treeChannels_cursor_changed(self.treeChannels)
                        break
                self.show_message( _('You have already subscribed to this podcast: %s') % ( 
                    saxutils.escape( old_channel.title), ), _('Already added'))
                waitdlg.destroy()
                return

        waitdlg = gtk.MessageDialog(self.gPodder, 0, gtk.MESSAGE_INFO, gtk.BUTTONS_NONE)
        waitdlg.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        waitdlg.set_title(_('Downloading episode list'))
        waitdlg.set_markup('<b><big>%s</big></b>' % waitdlg.get_title())
        waitdlg.format_secondary_text(_('Please wait while I am downloading episode information for %s') % result)
        waitpb = gtk.ProgressBar()
        if block:
            waitdlg.vbox.add(waitpb)
        waitdlg.show_all()
        waitdlg.set_response_sensitive(gtk.RESPONSE_CANCEL, False)

        self.entryAddChannel.set_text(_('Downloading feed...'))
        self.entryAddChannel.set_sensitive(False)
        self.btnAddChannel.set_sensitive(False)
        args = (result, self.add_new_channel_finish, authentication_tokens, ask_download_new, quiet, waitdlg)
        thread = Thread( target=self.add_new_channel_proc, args=args )
        thread.start()

        while block and thread.isAlive():
            while gtk.events_pending():
                gtk.main_iteration( False)
            waitpb.pulse()
            time.sleep(0.05)


    def add_new_channel_proc( self, url, callback, authentication_tokens, *callback_args):
        log( 'Adding new channel: %s', url)
        channel = error = None
        try:
            channel = podcastChannel.load(url=url, create=True, authentication_tokens=authentication_tokens)
        except HTTPAuthError, e:
            error = e
        except Exception, e:
            log('Error in podcastChannel.load(%s): %s', url, e, traceback=True, sender=self)

        util.idle_add( callback, channel, url, error, *callback_args )

    def add_new_channel_finish( self, channel, url, error, ask_download_new, quiet, waitdlg):
        if channel is not None:
            self.channels.append( channel)
            save_channels( self.channels)
            if not quiet:
                # download changed channels and select the new episode in the UI afterwards
                self.update_feed_cache(force_update=False, select_url_afterwards=channel.url)

            (username, password) = util.username_password_from_url( url)
            if username and self.show_confirmation( _('You have supplied <b>%s</b> as username and a password for this feed. Would you like to use the same authentication data for downloading episodes?') % ( saxutils.escape( username), ), _('Password authentication')):
                channel.username = username
                channel.password = password
                log('Saving authentication data for episode downloads..', sender = self)
                channel.save()
                # We need to update the channel list otherwise the authentication
                # data won't show up in the channel editor.
                # TODO: Only updated the newly added feed to save some cpu cycles
                self.channels = load_channels()

            if ask_download_new:
                new_episodes = channel.get_new_episodes()
                if len(new_episodes):
                    self.new_episodes_show(new_episodes)

        elif isinstance( error, HTTPAuthError ):
            response, auth_tokens = self.UsernamePasswordDialog(
                _('Feed requires authentication'), _('Please enter your username and password.'))

            if response:
                self.add_new_channel( url, authentication_tokens=auth_tokens )

        else:
            # Ok, the URL is not a channel, or there is some other
            # error - let's see if it's a web page or OPML file...
            try:
                data = urllib2.urlopen(url).read().lower()
                if '</opml>' in data:
                    # This looks like an OPML feed
                    self.on_item_import_from_file_activate(None, url)

                elif '</html>' in data:
                    # This looks like a web page
                    title = _('The URL is a website')
                    message = _('The URL you specified points to a web page. You need to find the "feed" URL of the podcast to add to gPodder. Do you want to visit this website now and look for the podcast feed URL?\n\n(Hint: Look for "XML feed", "RSS feed" or "Podcast feed" if you are unsure for what to look. If there is only an iTunes URL, try adding this one.)')
                    if self.show_confirmation(message, title):
                        util.open_website(url)

            except Exception, e:
                log('Error trying to handle the URL as OPML or web page: %s', e, sender=self)

            title = _('Error adding podcast')
            message = _('The podcast could not be added. Please check the spelling of the URL or try again later.')
            self.show_message( message, title)

        self.entryAddChannel.set_text(self.ENTER_URL_TEXT)
        self.entryAddChannel.set_sensitive(True)
        self.btnAddChannel.set_sensitive(True)
        self.update_podcasts_tab()
        waitdlg.destroy()


    def update_feed_cache_finish_callback(self, channels=None,
        notify_no_new_episodes=False, select_url_afterwards=None):

        db.commit()

        self.updating_feed_cache = False
        self.hboxUpdateFeeds.hide_all()
        self.btnUpdateFeeds.show_all()
        self.itemUpdate.set_sensitive(True)
        self.itemUpdateChannel.set_sensitive(True)

        # If we want to select a specific podcast (via its URL)
        # after the update, we give it to updateComboBox here to
        # select exactly this podcast after updating the view
        self.updateComboBox(selected_url=select_url_afterwards)

        if self.tray_icon:
            self.tray_icon.set_status(None)
            if self.minimized:
                new_episodes = []
                # look for new episodes to notify
                for channel in self.channels:
                    for episode in channel.get_new_episodes():
                        if not episode in self.already_notified_new_episodes:
                            new_episodes.append(episode)
                            self.already_notified_new_episodes.append(episode)
                # notify new episodes
                                
                if len(new_episodes) == 0:
                    if notify_no_new_episodes and self.tray_icon is not None:
                        msg = _('No new episodes available for download')
                        self.tray_icon.send_notification(msg)                        
                    return
                elif len(new_episodes) == 1:
                    title = _('gPodder has found %s') % (_('one new episode:'),)
                else:    
                    title = _('gPodder has found %s') % (_('%i new episodes:') % len(new_episodes))
                message = self.tray_icon.format_episode_list(new_episodes)

                #auto download new episodes
                if gl.config.auto_download_when_minimized:
                    message += '\n<i>(%s...)</i>' % _('downloading')
                    self.download_episode_list(new_episodes)
                self.tray_icon.send_notification(message, title)
                return

        # open the episodes selection dialog
        self.channels = load_channels()
        self.updateComboBox()
        if not self.feed_cache_update_cancelled:
            self.download_all_new(channels=channels)

    def update_feed_cache_callback(self, progressbar, title, position, count):
        progression = _('Updated %s (%d/%d)')%(title, position+1, count)
        progressbar.set_text(progression)
        if self.tray_icon:
            self.tray_icon.set_status(
                self.tray_icon.STATUS_UPDATING_FEED_CACHE, progression )
        if count > 0:
            progressbar.set_fraction(float(position)/float(count))

    def update_feed_cache_proc( self, channel, total_channels, semaphore,
        callback_proc, finish_proc):

        semaphore.acquire()
        if not self.feed_cache_update_cancelled:
            try:
                channel.update()
            except:
                log('Darn SQLite LOCK!', sender=self, traceback=True)

        # By the time we get here the update may have already been cancelled
        if not self.feed_cache_update_cancelled:
            callback_proc(channel.title, self.updated_feeds, total_channels)

        self.updated_feeds += 1
        self.treeview_channel_set_color( channel, 'default' )
        channel.update_flag = False

        semaphore.release()
        if self.updated_feeds == total_channels:
            finish_proc()

    def on_btnCancelFeedUpdate_clicked(self, widget):
        self.pbFeedUpdate.set_text(_('Cancelling...'))
        self.feed_cache_update_cancelled = True

    def update_feed_cache(self, channels=None, force_update=True,
        notify_no_new_episodes=False, select_url_afterwards=None):

        if self.updating_feed_cache: 
            return

        if not force_update:
            self.channels = load_channels()
            self.updateComboBox()
            return
        
        self.updating_feed_cache = True
        self.itemUpdate.set_sensitive(False)
        self.itemUpdateChannel.set_sensitive(False)

        if self.tray_icon:
            self.tray_icon.set_status(self.tray_icon.STATUS_UPDATING_FEED_CACHE)
        
        if channels is None:
            channels = self.channels

        if len(channels) == 1:
            text = _('Updating %d feed.')
        else:
            text = _('Updating %d feeds.')
        self.pbFeedUpdate.set_text( text % len(channels))
        self.pbFeedUpdate.set_fraction(0)

        # let's get down to business..
        callback_proc = lambda title, pos, count: util.idle_add( 
            self.update_feed_cache_callback, self.pbFeedUpdate, title, pos, count )
        finish_proc = lambda: util.idle_add( self.update_feed_cache_finish_callback,
            channels, notify_no_new_episodes, select_url_afterwards )

        self.updated_feeds = 0
        self.feed_cache_update_cancelled = False
        self.btnUpdateFeeds.hide_all()
        self.hboxUpdateFeeds.show_all()
        semaphore = Semaphore(gl.config.max_simulaneous_feeds_updating)

        for channel in channels:
            self.treeview_channel_set_color( channel, 'updating' )
            channel.update_flag = True
            args = (channel, len(channels), semaphore, callback_proc, finish_proc)
            thread = Thread( target = self.update_feed_cache_proc, args = args)
            thread.start()

    def treeview_channel_set_color( self, channel, color ):
        if self.treeChannels.get_model():
            if color in self.channel_colors:
                self.treeChannels.get_model().set(channel.iter, 8, self.channel_colors[color])
            else:
                self.treeChannels.get_model().set(channel.iter, 8, color)

    def on_gPodder_delete_event(self, widget, *args):
        """Called when the GUI wants to close the window
        Displays a confirmation dialog (and closes/hides gPodder)
        """

        downloading = services.download_status_manager.has_items()

        # Only iconify if we are using the window's "X" button,
        # but not when we are using "Quit" in the menu or toolbar
        if not gl.config.on_quit_ask and gl.config.on_quit_systray and self.tray_icon and widget.name not in ('toolQuit', 'itemQuit'):
            self.iconify_main_window()
        elif gl.config.on_quit_ask or downloading:
            if gpodder.interface == gpodder.MAEMO:
                result = self.show_confirmation(_('Do you really want to quit gPodder now?'))
                if result:
                    self.close_gpodder()
                else:
                    return True
            dialog = gtk.MessageDialog(self.gPodder, gtk.DIALOG_MODAL, gtk.MESSAGE_QUESTION, gtk.BUTTONS_NONE)
            dialog.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
            dialog.add_button(gtk.STOCK_QUIT, gtk.RESPONSE_CLOSE)

            title = _('Quit gPodder')
            if downloading:
                message = _('You are downloading episodes. If you close gPodder now, the downloads will be aborted.')
            else:
                message = _('Do you really want to quit gPodder now?')

            dialog.set_title(title)
            dialog.set_markup('<span weight="bold" size="larger">%s</span>\n\n%s'%(title, message))
            if not downloading:
                cb_ask = gtk.CheckButton(_("Don't ask me again"))
                dialog.vbox.pack_start(cb_ask)
                cb_ask.show_all()

            result = dialog.run()
            dialog.destroy()

            if result == gtk.RESPONSE_CLOSE:
                if not downloading and cb_ask.get_active() == True:
                    gl.config.on_quit_ask = False
                self.close_gpodder()
        else:
            self.close_gpodder()

        return True

    def close_gpodder(self):
        """ clean everything and exit properly
        """
        if self.channels:
            if save_channels(self.channels):
                if gl.config.my_gpodder_autoupload:
                    log('Uploading to my.gpodder.org on close', sender=self)
                    util.idle_add(self.on_upload_to_mygpo, None)
            else:
                self.show_message(_('Please check your permissions and free disk space.'), _('Error saving podcast list'))

        services.download_status_manager.cancel_all()
        self.gPodder.hide()
        while gtk.events_pending():
            gtk.main_iteration(False)

        db.close()

        self.gtk_main_quit()
        sys.exit( 0)

    def get_old_episodes(self):
        episodes = []
        for channel in self.channels:
            for episode in channel.get_downloaded_episodes():
                if episode.is_old() and not episode.is_locked and episode.is_played:
                    episodes.append(episode)
        return episodes

    def for_each_selected_episode_url( self, callback):
        ( model, paths ) = self.treeAvailable.get_selection().get_selected_rows()
        for path in paths:
            url = model.get_value( model.get_iter( path), 0)
            try:
                callback( url)
            except Exception, e:
                log( 'Warning: Error in for_each_selected_episode_url for URL %s: %s', url, e, sender = self)

        self.updateComboBox(only_selected_channel=True)

    def delete_episode_list( self, episodes, confirm = True):
        if len(episodes) == 0:
            return

        if len(episodes) == 1:
            message = _('Do you really want to delete this episode?')
        else:
            message = _('Do you really want to delete %d episodes?') % len(episodes)

        if confirm and self.show_confirmation( message, _('Delete episodes')) == False:
            return

        for episode in episodes:
            log('Deleting episode: %s', episode.title, sender = self)
            episode.delete_from_disk()

        self.download_status_updated()

    def on_itemRemoveOldEpisodes_activate( self, widget):
        columns = (
                ('title_and_description', None, None, _('Episode')),
                ('channel_prop', None, None, _('Podcast')),
                ('filesize_prop', 'length', gobject.TYPE_INT, _('Size')),
                ('pubdate_prop', 'pubDate', gobject.TYPE_INT, _('Released')),
                ('played_prop', None, None, _('Status')),
                ('age_prop', None, None, _('Downloaded')),
        )

        selection_buttons = {
                _('Select played'): lambda episode: episode.is_played,
                _('Select older than %d days') % gl.config.episode_old_age: lambda episode: episode.is_old(),
        }

        instructions = _('Select the episodes you want to delete from your hard disk.')

        episodes = []
        selected = []
        for channel in self.channels:
            for episode in channel.get_downloaded_episodes():
                if not episode.is_locked:
                    episodes.append(episode)
                    selected.append(episode.is_played)

        gPodderEpisodeSelector( title = _('Remove old episodes'), instructions = instructions, \
                                episodes = episodes, selected = selected, columns = columns, \
                                stock_ok_button = gtk.STOCK_DELETE, callback = self.delete_episode_list, \
                                selection_buttons = selection_buttons)

    def mark_selected_episodes_new(self):
        callback = lambda url: self.active_channel.find_episode(url).mark_new()
        self.for_each_selected_episode_url(callback)

    def mark_selected_episodes_old(self):
        callback = lambda url: self.active_channel.find_episode(url).mark_old()
        self.for_each_selected_episode_url(callback)

    def on_item_toggle_played_activate( self, widget, toggle = True, new_value = False):
        if toggle:
            callback = lambda url: db.mark_episode(url, is_played=True, toggle=True)
        else:
            callback = lambda url: db.mark_episode(url, is_played=new_value)

        self.for_each_selected_episode_url(callback)

    def on_item_toggle_lock_activate(self, widget, toggle=True, new_value=False):
        if toggle:
            callback = lambda url: db.mark_episode(url, is_locked=True, toggle=True)
        else:
            callback = lambda url: db.mark_episode(url, is_locked=new_value)

        self.for_each_selected_episode_url(callback)

    def on_channel_toggle_lock_activate(self, widget, toggle=True, new_value=False):

        self.active_channel.channel_is_locked = not self.active_channel.channel_is_locked
        db.update_channel_lock(self.active_channel)

        if self.active_channel.channel_is_locked:
            self.change_menu_item(self.channel_toggle_lock, gtk.STOCK_DIALOG_AUTHENTICATION, _('Allow deletion of all episodes'))
        else:
            self.change_menu_item(self.channel_toggle_lock, gtk.STOCK_DIALOG_AUTHENTICATION, _('Prohibit deletion of all episodes'))

        for episode in self.active_channel.get_all_episodes():
            db.mark_episode(episode.url, is_locked=self.active_channel.channel_is_locked)
        self.updateComboBox()


    def on_item_email_subscriptions_activate(self, widget):
        if not self.channels:
            self.show_message(_('Your subscription list is empty.'), _('Could not send list'))
        elif not gl.send_subscriptions():
            self.show_message(_('There was an error sending your subscription list via e-mail.'), _('Could not send list'))

    def on_itemUpdateChannel_activate(self, widget=None):
        self.update_feed_cache(channels=[self.active_channel,])

    def on_itemUpdate_activate(self, widget, notify_no_new_episodes=False):
        restore_from = can_restore_from_opml()

        if self.channels:
            self.update_feed_cache(notify_no_new_episodes=notify_no_new_episodes)
        elif restore_from is not None:
            title = _('Database upgrade required')
            message = _('gPodder is now using a new (much faster) database backend and needs to convert your current data. This can take some time. Start the conversion now?')
            if self.show_confirmation(message, title):
                add_callback = lambda url: self.add_new_channel(url, False, True)
                w = gtk.Dialog(_('Migrating to SQLite'), self.gPodder, 0, (gtk.STOCK_CLOSE, gtk.RESPONSE_ACCEPT))
                w.set_has_separator(False)
                w.set_response_sensitive(gtk.RESPONSE_ACCEPT, False)
                w.set_default_size(500, -1)
                pb = gtk.ProgressBar()
                l = gtk.Label()
                l.set_padding(6, 3)
                l.set_markup('<b><big>%s</big></b>' % _('SQLite migration'))
                l.set_alignment(0.0, 0.5)
                w.vbox.pack_start(l)
                l = gtk.Label()
                l.set_padding(6, 3)
                l.set_alignment(0.0, 0.5)
                l.set_text(_('Please wait while your settings are converted.'))
                w.vbox.pack_start(l)
                w.vbox.pack_start(pb)
                lb = gtk.Label()
                lb.set_ellipsize(pango.ELLIPSIZE_END)
                lb.set_alignment(0.0, 0.5)
                lb.set_padding(6, 6)
                w.vbox.pack_start(lb)

                def set_pb_status(pb, lb, fraction, text):
                    pb.set_fraction(float(fraction)/100.0)
                    pb.set_text('%.0f %%' % fraction)
                    lb.set_markup('<i>%s</i>' % saxutils.escape(text))
                    while gtk.events_pending():
                        gtk.main_iteration(False)
                status_callback = lambda fraction, text: set_pb_status(pb, lb, fraction, text)
                get_localdb = lambda channel: LocalDBReader(channel.url).read(channel.index_file)
                w.show_all()
                start = datetime.datetime.now()
                gl.migrate_to_sqlite(add_callback, status_callback, load_channels, get_localdb)
                # Refresh the view with the updated episodes
                self.updateComboBox()
                time_taken = str(datetime.datetime.now()-start)
                status_callback(100.0, _('Migration finished in %s') % time_taken)
                w.set_response_sensitive(gtk.RESPONSE_ACCEPT, True)
                w.run()
                w.destroy()
        else:
            gPodderWelcome(center_on_widget=self.gPodder, show_example_podcasts_callback=self.on_itemImportChannels_activate, setup_my_gpodder_callback=self.on_download_from_mygpo)

    def download_episode_list( self, episodes):
        services.download_status_manager.start_batch_mode()
        for episode in episodes:
            log('Downloading episode: %s', episode.title, sender = self)
            filename = episode.local_filename()
            if not episode.was_downloaded(and_exists=True) and not services.download_status_manager.is_download_in_progress( episode.url):
                download.DownloadThread( episode.channel, episode, self.notification).start()
        services.download_status_manager.end_batch_mode()

    def new_episodes_show(self, episodes):
        columns = (
                ('title_and_description', None, None, _('Episode')),
                ('channel_prop', None, None, _('Podcast')),
                ('filesize_prop', 'length', gobject.TYPE_INT, _('Size')),
                ('pubdate_prop', 'pubDate', gobject.TYPE_INT, _('Released')),
        )

        if len(episodes) > 0:
            instructions = _('Select the episodes you want to download now.')

            gPodderEpisodeSelector(title=_('New episodes available'), instructions=instructions, \
                                   episodes=episodes, columns=columns, selected_default=True, \
                                   stock_ok_button = 'gpodder-download', \
                                   callback=self.download_episode_list, \
                                   remove_callback=lambda e: e.mark_old(), \
                                   remove_action=_('Never download'), \
                                   remove_finished=self.episode_new_status_changed)
        else:
            title = _('No new episodes')
            message = _('No new episodes to download.\nPlease check for new episodes later.')
            self.show_message(message, title)

    def on_itemDownloadAllNew_activate(self, widget, *args):
        self.download_all_new()

    def download_all_new(self, channels=None):
        if channels is None:
            channels = self.channels
        episodes = []
        for channel in channels:
            for episode in channel.get_new_episodes():
                episodes.append(episode)
        self.new_episodes_show(episodes)

    def get_all_episodes(self, exclude_nonsignificant=True ):
        """'exclude_nonsignificant' will exclude non-downloaded episodes
            and all episodes from channels that are set to skip when syncing"""
        episode_list = []
        for channel in self.channels:
            if not channel.sync_to_devices and exclude_nonsignificant:
                log('Skipping channel: %s', channel.title, sender=self)
                continue
            for episode in channel.get_all_episodes():
                if episode.was_downloaded(and_exists=True) or not exclude_nonsignificant:
                    episode_list.append(episode)
        return episode_list

    def ipod_delete_played(self, device):
        all_episodes = self.get_all_episodes( exclude_nonsignificant=False )
        episodes_on_device = device.get_all_tracks()
        for local_episode in all_episodes:
            device_episode = device.episode_on_device(local_episode)
            if device_episode and ( local_episode.is_played and not local_episode.is_locked
                or local_episode.state == db.STATE_DELETED ):
                log("mp3_player_delete_played: removing %s" % device_episode.title)
                device.remove_track(device_episode)

    def on_sync_to_ipod_activate(self, widget, episodes=None):
        # make sure gpod is available before even trying to sync
        if gl.config.device_type == 'ipod' and not sync.gpod_available:
            title = _('Cannot Sync To iPod')
            message = _('Please install the libgpod python bindings (python-gpod) and restart gPodder to continue.')
            self.notification( message, title )
            return
        elif gl.config.device_type == 'mtp' and not sync.pymtp_available:
            title = _('Cannot sync to MTP device')
            message = _('Please install the libmtp python bindings (python-pymtp) and restart gPodder to continue.')
            self.notification( message, title )
            return

        device = sync.open_device()
        device.register( 'post-done', self.sync_to_ipod_completed )

        if device is None:
            title = _('No device configured')
            message = _('To use the synchronization feature, please configure your device in the preferences dialog first.')
            self.notification(message, title)
            return

        if not device.open():
            title = _('Cannot open device')
            message = _('There has been an error opening your device.')
            self.notification(message, title)
            return

        if gl.config.ipod_purge_old_episodes:
            device.purge()

        sync_all_episodes = not bool(episodes)

        if episodes is None:
            episodes = self.get_all_episodes()

        # make sure we have enough space on the device
        total_size = 0
        free_space = device.get_free_space()
        for episode in episodes:
            if not device.episode_on_device(episode) and not (sync_all_episodes and gl.config.only_sync_not_played and episode.is_played):
                total_size += util.calculate_size(str(episode.local_filename()))

        if total_size > free_space:
            # can be negative because of the 10 MiB for reserved for the iTunesDB
            free_space = max( free_space, 0 )
            log('(gpodder.sync) Not enough free space. Transfer size = %d, Free space = %d', total_size, free_space)
            title = _('Not enough space left on device.')
            message = _('%s remaining on device.\nPlease free up %s and try again.' % (
                util.format_filesize( free_space ), util.format_filesize( total_size - free_space )))
            self.notification(message, title)
        else:
            # start syncing!
            gPodderSync(device=device, gPodder=self)
            Thread(target=self.sync_to_ipod_thread, args=(widget, device, sync_all_episodes, episodes)).start()
            if self.tray_icon:
                self.tray_icon.set_synchronisation_device(device)

    def sync_to_ipod_completed(self, device, successful_sync):
        device.unregister( 'post-done', self.sync_to_ipod_completed )

        if self.tray_icon:
            self.tray_icon.release_synchronisation_device()
 
        if not successful_sync:
            title = _('Error closing device')
            message = _('There has been an error closing your device.')
            self.notification(message, title)

        # update model for played state updates after sync
        util.idle_add(self.updateComboBox)

    def sync_to_ipod_thread(self, widget, device, sync_all_episodes, episodes=None):
        if sync_all_episodes:
            device.add_tracks(episodes)
            # 'only_sync_not_played' must be used or else all the played
            #  tracks will be copied then immediately deleted
            if gl.config.mp3_player_delete_played and gl.config.only_sync_not_played:
                self.ipod_delete_played(device)
        else:
            device.add_tracks(episodes, force_played=True)
        device.close()

    def ipod_cleanup_callback(self, device, tracks):
        title = _('Delete podcasts from device?')
        message = _('The selected episodes will be removed from your device. This cannot be undone. Files in your gPodder library will be unaffected. Do you really want to delete these episodes from your device?')
        if len(tracks) > 0 and self.show_confirmation(message, title):
            gPodderSync(device=device, gPodder=self)
            Thread(target=self.ipod_cleanup_thread, args=[device, tracks]).start()

    def ipod_cleanup_thread(self, device, tracks):
        device.remove_tracks(tracks)
 
        if not device.close():
            title = _('Error closing device')
            message = _('There has been an error closing your device.')
            gobject.idle_add(self.show_message, message, title)

    def on_cleanup_ipod_activate(self, widget, *args):
        columns = (
                ('title', None, None, _('Episode')),
                ('podcast', None, None, _('Podcast')),
                ('filesize', None, None, _('Size')),
                ('modified', None, None, _('Copied')),
                ('playcount', None, None, _('Play count')),
                ('released', None, None, _('Released')),
        )

        device = sync.open_device()

        if device is None:
            title = _('No device configured')
            message = _('To use the synchronization feature, please configure your device in the preferences dialog first.')
            self.show_message(message, title)
            return

        if not device.open():
            title = _('Cannot open device')
            message = _('There has been an error opening your device.')
            self.show_message(message, title)
            return

        tracks = device.get_all_tracks()
        if len(tracks) > 0:
            remove_tracks_callback = lambda tracks: self.ipod_cleanup_callback(device, tracks)
            wanted_columns = []
            for key, sort_name, sort_type, caption in columns:
                want_this_column = False
                for track in tracks:
                    if getattr(track, key) is not None:
                        want_this_column = True
                        break

                if want_this_column:
                    wanted_columns.append((key, sort_name, sort_type, caption))
            title = _('Remove podcasts from device')
            instructions = _('Select the podcast episodes you want to remove from your device.')
            gPodderEpisodeSelector(title=title, instructions=instructions, episodes=tracks, columns=wanted_columns, \
                                   stock_ok_button=gtk.STOCK_DELETE, callback=remove_tracks_callback, tooltip_attribute=None)
        else:
            title = _('No files on device')
            message = _('The devices contains no files to be removed.')
            self.show_message(message, title)
            device.close()

    def on_manage_device_playlist(self, widget):
        # make sure gpod is available before even trying to sync
        if gl.config.device_type == 'ipod' and not sync.gpod_available:
            title = _('Cannot manage iPod playlist')
            message = _('This feature is not available for iPods.')
            self.notification( message, title )
            return
        elif gl.config.device_type == 'mtp' and not sync.pymtp_available:
            title = _('Cannot manage MTP device playlist')
            message = _('This feature is not available for MTP devices.')
            self.notification( message, title )
            return

        device = sync.open_device()

        if device is None:
            title = _('No device configured')
            message = _('To use the playlist feature, please configure your Filesystem based MP3-Player in the preferences dialog first.')
            self.notification(message, title)
            return

        if not device.open():
            title = _('Cannot open device')
            message = _('There has been an error opening your device.')
            self.notification(message, title)
            return

        gPodderPlaylist(device=device, gPodder=self)
        device.close()

    def show_hide_tray_icon(self):
        if gl.config.display_tray_icon and have_trayicon and self.tray_icon is None:
            self.tray_icon = trayicon.GPodderStatusIcon(self, scalable_dir)
        elif not gl.config.display_tray_icon and self.tray_icon is not None:
            self.tray_icon.set_visible(False)
            del self.tray_icon
            self.tray_icon = None

        if gl.config.minimize_to_tray and self.tray_icon:
            self.tray_icon.set_visible(self.minimized)
        elif self.tray_icon:
            self.tray_icon.set_visible(True)

    def on_itemShowToolbar_activate(self, widget):
        gl.config.show_toolbar = self.itemShowToolbar.get_active()

    def on_itemShowDescription_activate(self, widget):
        gl.config.episode_list_descriptions = self.itemShowDescription.get_active()

    def update_item_device( self):
        if gl.config.device_type != 'none':
            self.itemDevice.show_all()
            (label,) = self.itemDevice.get_children()
            label.set_text(gl.get_device_name())
        else:
            self.itemDevice.hide_all()

    def properties_closed( self):
        self.show_hide_tray_icon()
        self.update_item_device()
        self.updateComboBox()

    def on_itemPreferences_activate(self, widget, *args):
        if gpodder.interface == gpodder.GUI:
            gPodderProperties(callback_finished=self.properties_closed, user_apps_reader=self.user_apps_reader)
        else:
            gPodderMaemoPreferences()

    def on_itemDependencies_activate(self, widget):
        gPodderDependencyManager()

    def on_add_new_google_search(self, widget, *args):
        def add_google_video_search(query):
            self.add_new_channel('http://video.google.com/videofeed?type=search&q='+urllib.quote(query)+'&so=1&num=250&output=rss')

        gPodderAddPodcastDialog(url_callback=add_google_video_search, custom_title=_('Add Google Video search'), custom_label=_('Search for:'))

    def require_my_gpodder_authentication(self):
        if not gl.config.my_gpodder_username or not gl.config.my_gpodder_password:
            success, authentication = self.UsernamePasswordDialog(_('Login to my.gpodder.org'), _('Please enter your e-mail address and your password.'), username=gl.config.my_gpodder_username, password=gl.config.my_gpodder_password, username_prompt=_('E-Mail Address'), register_callback=lambda: util.open_website('http://my.gpodder.org/register'))
            if success and authentication[0] and authentication[1]:
                gl.config.my_gpodder_username, gl.config.my_gpodder_password = authentication
                return True
            else:
                return False

        return True
    
    def my_gpodder_offer_autoupload(self):
        if not gl.config.my_gpodder_autoupload:
            if self.show_confirmation(_('gPodder can automatically upload your subscription list to my.gpodder.org when you close it. Do you want to enable this feature?'), _('Upload subscriptions on quit')):
                gl.config.my_gpodder_autoupload = True
    
    def on_download_from_mygpo(self, widget):
        if self.require_my_gpodder_authentication():
            client = my.MygPodderClient(gl.config.my_gpodder_username, gl.config.my_gpodder_password)
            opml_data = client.download_subscriptions()
            if len(opml_data) > 0:
                fp = open(gl.channel_opml_file, 'w')
                fp.write(opml_data)
                fp.close()
                (added, skipped) = (0, 0)
                i = opml.Importer(gl.channel_opml_file)
                for item in i.items:
                    url = item['url']
                    if url not in (c.url for c in self.channels):
                        self.add_new_channel(url, ask_download_new=False, block=True)
                        added += 1
                    else:
                        log('Already added: %s', url, sender=self)
                        skipped += 1
                self.updateComboBox()
                if added > 0:
                    self.show_message(_('Added %d new subscriptions and skipped %d existing ones.') % (added, skipped), _('Result of subscription download'))
                elif widget is not None:
                    self.show_message(_('Your local subscription list is up to date.'), _('Result of subscription download'))
                self.my_gpodder_offer_autoupload()
            else:
                gl.config.my_gpodder_password = ''
                self.on_download_from_mygpo(widget)
        else:
            self.show_message(_('Please set up your username and password first.'), _('Username and password needed'))

    def on_upload_to_mygpo(self, widget):
        if self.require_my_gpodder_authentication():
            client = my.MygPodderClient(gl.config.my_gpodder_username, gl.config.my_gpodder_password)
            save_channels(self.channels)
            success, messages = client.upload_subscriptions(gl.channel_opml_file)
            if widget is not None:
                self.show_message('\n'.join(messages), _('Results of upload'))
                if not success:
                    gl.config.my_gpodder_password = ''
                    self.on_upload_to_mygpo(widget)
                else:
                    self.my_gpodder_offer_autoupload()
            elif not success:
                log('Upload to my.gpodder.org failed, but widget is None!', sender=self)
        elif widget is not None:
            self.show_message(_('Please set up your username and password first.'), _('Username and password needed'))

    def on_itemAddChannel_activate(self, widget, *args):
        gPodderAddPodcastDialog(url_callback=self.add_new_channel)

    def on_itemEditChannel_activate(self, widget, *args):
        if self.active_channel is None:
            title = _('No podcast selected')
            message = _('Please select a podcast in the podcasts list to edit.')
            self.show_message( message, title)
            return

        gPodderChannel(channel=self.active_channel, callback_closed=lambda: self.updateComboBox(only_selected_channel=True), callback_change_url=self.change_channel_url)

    def change_channel_url(self, old_url, new_url):
        channel = None
        try:
            channel = podcastChannel.load(url=new_url, create=True)
        except:
            channel = None

        if channel is None:
            self.show_message(_('The specified URL is invalid. The old URL has been used instead.'), _('Invalid URL'))
            return

        for channel in self.channels:
            if channel.url == old_url:
                log('=> change channel url from %s to %s', old_url, new_url)
                old_save_dir = channel.save_dir
                channel.url = new_url
                new_save_dir = channel.save_dir
                log('old save dir=%s', old_save_dir, sender=self)
                log('new save dir=%s', new_save_dir, sender=self)
                files = glob.glob(os.path.join(old_save_dir, '*'))
                log('moving %d files to %s', len(files), new_save_dir, sender=self)
                for file in files:
                    log('moving %s', file, sender=self)
                    shutil.move(file, new_save_dir)
                try:
                    os.rmdir(old_save_dir)
                except:
                    log('Warning: cannot delete %s', old_save_dir, sender=self)

        save_channels(self.channels)
        # update feed cache and select the podcast with the new URL afterwards
        self.update_feed_cache(force_update=False, select_url_afterwards=new_url)

    def on_itemRemoveChannel_activate(self, widget, *args):
        try:
            if gpodder.interface == gpodder.GUI:
                dialog = gtk.MessageDialog(self.gPodder, gtk.DIALOG_MODAL, gtk.MESSAGE_QUESTION, gtk.BUTTONS_NONE)
                dialog.add_button(gtk.STOCK_NO, gtk.RESPONSE_NO)
                dialog.add_button(gtk.STOCK_YES, gtk.RESPONSE_YES)

                title = _('Remove podcast and episodes?')
                message = _('Do you really want to remove <b>%s</b> and all downloaded episodes?') % saxutils.escape(self.active_channel.title)
             
                dialog.set_title(title)
                dialog.set_markup('<span weight="bold" size="larger">%s</span>\n\n%s'%(title, message))
            
                cb_ask = gtk.CheckButton(_('Do not delete my downloaded episodes'))
                dialog.vbox.pack_start(cb_ask)
                cb_ask.show_all()
                affirmative = gtk.RESPONSE_YES
            elif gpodder.interface == gpodder.MAEMO:
                cb_ask = gtk.CheckButton('') # dummy check button
                dialog = hildon.Note('confirmation', (self.gPodder, _('Do you really want to remove this podcast and all downloaded episodes?')))
                affirmative = gtk.RESPONSE_OK

            result = dialog.run()
            dialog.destroy()

            if result == affirmative:
                # delete downloaded episodes only if checkbox is unchecked
                if cb_ask.get_active() == False:
                    self.active_channel.remove_downloaded()
                else:
                    log('Not removing downloaded episodes', sender=self)

                # only delete partial files if we do not have any downloads in progress
                delete_partial = not services.download_status_manager.has_items()
                gl.clean_up_downloads(delete_partial)
                
                # cancel any active downloads from this channel
                if not delete_partial:
                    for episode in self.active_channel.get_all_episodes():
                        services.download_status_manager.cancel_by_url(episode.url)

                # get the URL of the podcast we want to select next
                position = self.channels.index(self.active_channel)
                if position == len(self.channels)-1:
                    # this is the last podcast, so select the URL
                    # of the item before this one (i.e. the "new last")
                    select_url = self.channels[position-1].url
                else:
                    # there is a podcast after the deleted one, so
                    # we simply select the one that comes after it
                    select_url = self.channels[position+1].url
                
                # Remove the channel
                self.active_channel.delete()
                self.channels.remove(self.active_channel)
                save_channels(self.channels)

                # Re-load the channels and select the desired new channel
                self.update_feed_cache(force_update=False, select_url_afterwards=select_url)
        except:
            log('There has been an error removing the channel.', traceback=True, sender=self)
        self.update_podcasts_tab()

    def get_opml_filter(self):
        filter = gtk.FileFilter()
        filter.add_pattern('*.opml')
        filter.add_pattern('*.xml')
        filter.set_name(_('OPML files')+' (*.opml, *.xml)')
        return filter

    def on_item_import_from_file_activate(self, widget, filename=None):
        if filename is None:
            if gpodder.interface == gpodder.GUI:
                dlg = gtk.FileChooserDialog(title=_('Import from OPML'), parent=None, action=gtk.FILE_CHOOSER_ACTION_OPEN)
                dlg.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
                dlg.add_button(gtk.STOCK_OPEN, gtk.RESPONSE_OK)
            elif gpodder.interface == gpodder.MAEMO:
                dlg = hildon.FileChooserDialog(self.gPodder, gtk.FILE_CHOOSER_ACTION_OPEN)
            dlg.set_filter(self.get_opml_filter())
            response = dlg.run()
            filename = None
            if response == gtk.RESPONSE_OK:
                filename = dlg.get_filename()
            dlg.destroy()

        if filename is not None:
            gPodderOpmlLister(custom_title=_('Import podcasts from OPML file'), hide_url_entry=True).get_channels_from_url(filename, lambda url: self.add_new_channel(url,False,block=True), lambda: self.on_itemDownloadAllNew_activate(self.gPodder))

    def on_itemExportChannels_activate(self, widget, *args):
        if not self.channels:
            title = _('Nothing to export')
            message = _('Your list of podcast subscriptions is empty. Please subscribe to some podcasts first before trying to export your subscription list.')
            self.show_message( message, title)
            return

        if gpodder.interface == gpodder.GUI:
            dlg = gtk.FileChooserDialog(title=_('Export to OPML'), parent=self.gPodder, action=gtk.FILE_CHOOSER_ACTION_SAVE)
            dlg.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
            dlg.add_button(gtk.STOCK_SAVE, gtk.RESPONSE_OK)
        elif gpodder.interface == gpodder.MAEMO:
            dlg = hildon.FileChooserDialog(self.gPodder, gtk.FILE_CHOOSER_ACTION_SAVE)
        dlg.set_filter(self.get_opml_filter())
        response = dlg.run()
        if response == gtk.RESPONSE_OK:
            filename = dlg.get_filename()
            dlg.destroy()
            exporter = opml.Exporter( filename)
            if exporter.write(self.channels):
                if len(self.channels) == 1:
                    title = _('One subscription exported')
                else:
                    title = _('%d subscriptions exported') % len(self.channels)
                self.show_message(_('Your podcast list has been successfully exported.'), title)
            else:
                self.show_message( _('Could not export OPML to file. Please check your permissions.'), _('OPML export failed'))
        else:
            dlg.destroy()

    def on_itemImportChannels_activate(self, widget, *args):
        gPodderOpmlLister().get_channels_from_url(gl.config.opml_url, lambda url: self.add_new_channel(url,False,block=True), lambda: self.on_itemDownloadAllNew_activate(self.gPodder))

    def on_homepage_activate(self, widget, *args):
        util.open_website(app_website)

    def on_wiki_activate(self, widget, *args):
        util.open_website('http://wiki.gpodder.org/')

    def on_bug_tracker_activate(self, widget, *args):
        util.open_website('http://bugs.gpodder.org/')

    def on_itemAbout_activate(self, widget, *args):
        dlg = gtk.AboutDialog()
        dlg.set_name(app_name.replace('p', 'P')) # gpodder->gPodder
        dlg.set_version( app_version)
        dlg.set_copyright( app_copyright)
        dlg.set_website( app_website)
        dlg.set_translator_credits( _('translator-credits'))
        dlg.connect( 'response', lambda dlg, response: dlg.destroy())

        if gpodder.interface == gpodder.GUI:
            # For the "GUI" version, we add some more
            # items to the about dialog (credits and logo)
            dlg.set_authors(app_authors)
            try:
                dlg.set_logo(gtk.gdk.pixbuf_new_from_file(scalable_dir))
            except:
                pass
        
        dlg.run()

    def on_wNotebook_switch_page(self, widget, *args):
        page_num = args[1]
        if gpodder.interface == gpodder.MAEMO:
            page = self.wNotebook.get_nth_page(page_num)
            tab_label = self.wNotebook.get_tab_label(page).get_text()
            if page_num == 0 and self.active_channel is not None:
                self.set_title(self.active_channel.title)
            else:
                self.set_title(tab_label)
        if page_num == 0:
            self.play_or_download()
        else:
            self.toolDownload.set_sensitive( False)
            self.toolPlay.set_sensitive( False)
            self.toolTransfer.set_sensitive( False)
            self.toolCancel.set_sensitive( services.download_status_manager.has_items())

    def on_treeChannels_row_activated(self, widget, *args):
        # double-click action of the podcast list
        pass

    def on_treeChannels_cursor_changed(self, widget, *args):
        ( model, iter ) = self.treeChannels.get_selection().get_selected()

        if model is not None and iter != None:
            id = model.get_path( iter)[0]
            self.active_channel = self.channels[id]

            if gpodder.interface == gpodder.MAEMO:
                self.set_title(self.active_channel.title)
            self.itemEditChannel.show_all()
            self.itemRemoveChannel.show_all()
            self.channel_toggle_lock.show_all()
            if self.active_channel.channel_is_locked:
                self.change_menu_item(self.channel_toggle_lock, gtk.STOCK_DIALOG_AUTHENTICATION, _('Allow deletion of all episodes'))
            else:
                self.change_menu_item(self.channel_toggle_lock, gtk.STOCK_DIALOG_AUTHENTICATION, _('Prohibit deletion of all episodes'))

        else:
            self.active_channel = None
            self.itemEditChannel.hide_all()
            self.itemRemoveChannel.hide_all()
            self.channel_toggle_lock.hide_all()

        self.updateTreeView(False)

    def on_entryAddChannel_changed(self, widget, *args):
        active = self.entryAddChannel.get_text() not in ('', self.ENTER_URL_TEXT)
        self.btnAddChannel.set_sensitive( active)

    def on_btnAddChannel_clicked(self, widget, *args):
        url = self.entryAddChannel.get_text()
        self.entryAddChannel.set_text('')
        self.add_new_channel( url)

    def on_btnEditChannel_clicked(self, widget, *args):
        self.on_itemEditChannel_activate( widget, args)

    def on_treeAvailable_row_activated(self, widget, path=None, view_column=None):
        """
        What this function does depends on from which widget it is called.
        It gets the selected episodes of the current podcast and runs one
        of the following actions on them:

          * Transfer (to MP3 player, iPod, etc..)
          * Playback/open files
          * Show the episode info dialog
          * Download episodes
        """
        try:
            selection = self.treeAvailable.get_selection()
            (model, paths) = selection.get_selected_rows()

            wname = widget.get_name()
            do_transfer = (wname in ('itemTransferSelected', 'toolTransfer'))
            do_playback = (wname in ('itemPlaySelected', 'itemOpenSelected', 'toolPlay'))
            do_epdialog = (wname in ('treeAvailable', 'item_episode_details'))

            episodes = []
            for path in paths:
                it = model.get_iter(path)
                url = model.get_value(it, 0)
                episode = self.active_channel.find_episode(url)
                episodes.append(episode)

            if len(episodes) == 0:
                log('No episodes selected', sender=self)

            if do_transfer:
                self.on_sync_to_ipod_activate(widget, episodes)
            elif do_playback:
                for episode in episodes:
                    # Make sure to mark the episode as downloaded
                    if os.path.exists(episode.local_filename()):
                        episode.channel.addDownloadedItem(episode)
                        self.playback_episode(episode)
                    elif gl.config.enable_streaming:
                        self.playback_episode(episode, stream=True)
            elif do_epdialog:
                play_callback = lambda: self.playback_episode(episode)
                download_callback = lambda: self.download_episode_list([episode])
                gPodderEpisode(episode=episode, download_callback=download_callback, play_callback=play_callback)
            else:
                self.download_episode_list(episodes)
        except:
            log('Error in on_treeAvailable_row_activated', traceback=True, sender=self)

    def on_treeAvailable_button_release_event(self, widget, *args):
        self.play_or_download()

    def auto_update_procedure(self, first_run=False):
        log('auto_update_procedure() got called', sender=self)
        if not first_run and gl.config.auto_update_feeds and self.minimized:
            self.update_feed_cache(force_update=True)

        next_update = 60*1000*gl.config.auto_update_frequency
        gobject.timeout_add(next_update, self.auto_update_procedure)

    def on_treeDownloads_row_activated(self, widget, *args):
        cancel_urls = []

        if self.wNotebook.get_current_page() > 0:
            # Use the download list treeview + model
            ( tree, column ) = ( self.treeDownloads, 3 )
        else:
            # Use the available podcasts treeview + model
            ( tree, column ) = ( self.treeAvailable, 0 )

        selection = tree.get_selection()
        (model, paths) = selection.get_selected_rows()
        for path in paths:
            url = model.get_value( model.get_iter( path), column)
            cancel_urls.append( url)

        if len( cancel_urls) == 0:
            log('Nothing selected.', sender = self)
            return

        if len( cancel_urls) == 1:
            title = _('Cancel download?')
            message = _("Cancelling this download will remove the partially downloaded file and stop the download.")
        else:
            title = _('Cancel downloads?')
            message = _("Cancelling the download will stop the %d selected downloads and remove partially downloaded files.") % selection.count_selected_rows()

        if self.show_confirmation( message, title):
            services.download_status_manager.start_batch_mode()
            for url in cancel_urls:
                services.download_status_manager.cancel_by_url( url)
            services.download_status_manager.end_batch_mode()

    def on_btnCancelDownloadStatus_clicked(self, widget, *args):
        self.on_treeDownloads_row_activated( widget, None)

    def on_btnCancelAll_clicked(self, widget, *args):
        self.treeDownloads.get_selection().select_all()
        self.on_treeDownloads_row_activated( self.toolCancel, None)
        self.treeDownloads.get_selection().unselect_all()

    def on_btnDownloadedDelete_clicked(self, widget, *args):
        if self.active_channel is None:
            return

        channel_url = self.active_channel.url
        selection = self.treeAvailable.get_selection()
        ( model, paths ) = selection.get_selected_rows()

        if selection.count_selected_rows() == 0:
            log( 'Nothing selected - will not remove any downloaded episode.')
            return

        if selection.count_selected_rows() == 1:
            episode_title = saxutils.escape(model.get_value(model.get_iter(paths[0]), 1))

            episode = db.load_episode(model.get_value(model.get_iter(paths[0]), 0))
            if episode['is_locked']:
                title = _('%s is locked') % episode_title
                message = _('You cannot delete this locked episode. You must unlock it before you can delete it.')
                self.notification(message, title)
                return

            title = _('Remove %s?') % episode_title
            message = _("If you remove this episode, it will be deleted from your computer. If you want to listen to this episode again, you will have to re-download it.")
        else:
            title = _('Remove %d episodes?') % selection.count_selected_rows()
            message = _('If you remove these episodes, they will be deleted from your computer. If you want to listen to any of these episodes again, you will have to re-download the episodes in question.')

        locked_count = 0
        for path in paths:
            episode = db.load_episode(model.get_value(model.get_iter(path), 0))
            if episode['is_locked']:
                locked_count += 1

        if selection.count_selected_rows() == locked_count:
            title = _('Episodes are locked')
            message = _('The selected episodes are locked. Please unlock the episodes that you want to delete before trying to delete them.')
            self.notification(message, title)
            return
        elif locked_count > 0:
            title = _('Remove %d out of %d episodes?') % (selection.count_selected_rows() - locked_count, selection.count_selected_rows())
            message = _('The selection contains locked episodes that will not be deleted. If you want to listen to the deleted episodes, you will have to re-download them.')
            
        # if user confirms deletion, let's remove some stuff ;)
        if self.show_confirmation( message, title):
            try:
                # iterate over the selection, see also on_treeDownloads_row_activated
                for path in paths:
                    url = model.get_value( model.get_iter( path), 0)
                    self.active_channel.delete_episode_by_url( url)
      
                # now, clear local db cache so we can re-read it
                self.updateComboBox()
            except:
                log( 'Error while deleting (some) downloads.')

        # only delete partial files if we do not have any downloads in progress
        delete_partial = not services.download_status_manager.has_items()
        gl.clean_up_downloads(delete_partial)
        self.updateTreeView()

    def on_key_press(self, widget, event):
        # Allow tab switching with Ctrl + PgUp/PgDown
        if event.state & gtk.gdk.CONTROL_MASK:
            if event.keyval == gtk.keysyms.Page_Up:
                self.wNotebook.prev_page()
                return True
            elif event.keyval == gtk.keysyms.Page_Down:
                self.wNotebook.next_page()
                return True

        # After this code we only handle Maemo hardware keys,
        # so if we are not a Maemo app, we don't do anything
        if gpodder.interface != gpodder.MAEMO:
            return False
        
        if event.keyval == gtk.keysyms.F6:
            if self.fullscreen:
                self.window.unfullscreen()
            else:
                self.window.fullscreen()
        if event.keyval == gtk.keysyms.Escape:
            new_visibility = not self.vboxChannelNavigator.get_property('visible')
            self.vboxChannelNavigator.set_property('visible', new_visibility)
            self.column_size.set_visible(not new_visibility)
            self.column_released.set_visible(not new_visibility)
        
        diff = 0
        if event.keyval == gtk.keysyms.F7: #plus
            diff = 1
        elif event.keyval == gtk.keysyms.F8: #minus
            diff = -1

        if diff != 0:
            selection = self.treeChannels.get_selection()
            (model, iter) = selection.get_selected()
            selection.select_path(((model.get_path(iter)[0]+diff)%len(model),))
            self.on_treeChannels_cursor_changed(self.treeChannels)
        
    def window_state_event(self, widget, event):
        if event.new_window_state & gtk.gdk.WINDOW_STATE_FULLSCREEN:
            self.fullscreen = True
        else:
            self.fullscreen = False
            
        old_minimized = self.minimized

        self.minimized = bool(event.new_window_state & gtk.gdk.WINDOW_STATE_ICONIFIED)
        if gpodder.interface == gpodder.MAEMO:
            self.minimized = bool(event.new_window_state & gtk.gdk.WINDOW_STATE_WITHDRAWN)

        if old_minimized != self.minimized and self.tray_icon:
            self.gPodder.set_skip_taskbar_hint(self.minimized)
        elif not self.tray_icon:
            self.gPodder.set_skip_taskbar_hint(False)

        if gl.config.minimize_to_tray and self.tray_icon:
            self.tray_icon.set_visible(self.minimized)
    
    def uniconify_main_window(self):
        if self.minimized:
            self.gPodder.present()
 
    def iconify_main_window(self):
        if not self.minimized:
            self.gPodder.iconify()          

    def update_podcasts_tab(self):
        if len(self.channels):
            self.label2.set_text(_('Podcasts (%d)') % len(self.channels))
        else:
            self.label2.set_text(_('Podcasts'))

class gPodderChannel(GladeWidget):
    finger_friendly_widgets = ['btn_website', 'btnOK', 'channel_description', 'label19', 'label37', 'label31']
    
    def new(self):
        global WEB_BROWSER_ICON
        self.changed = False
        self.image3167.set_property('icon-name', WEB_BROWSER_ICON)
        self.gPodderChannel.set_title( self.channel.title)
        self.entryTitle.set_text( self.channel.title)
        self.entryURL.set_text( self.channel.url)

        self.LabelDownloadTo.set_text( self.channel.save_dir)
        self.LabelWebsite.set_text( self.channel.link)

        self.cbNoSync.set_active( not self.channel.sync_to_devices)
        self.musicPlaylist.set_text(self.channel.device_playlist_name)
        if self.channel.username:
            self.FeedUsername.set_text( self.channel.username)
        if self.channel.password:
            self.FeedPassword.set_text( self.channel.password)

        services.cover_downloader.register('cover-available', self.cover_download_finished)
        services.cover_downloader.request_cover(self.channel)

        # Hide the website button if we don't have a valid URL
        if not self.channel.link:
            self.btn_website.hide_all()
        
        b = gtk.TextBuffer()
        b.set_text( self.channel.description)
        self.channel_description.set_buffer( b)

        #Add Drag and Drop Support
        flags = gtk.DEST_DEFAULT_ALL
        targets = [ ('text/uri-list', 0, 2), ('text/plain', 0, 4) ]
        actions = gtk.gdk.ACTION_DEFAULT | gtk.gdk.ACTION_COPY
        self.vboxCoverEditor.drag_dest_set( flags, targets, actions)
        self.vboxCoverEditor.connect( 'drag_data_received', self.drag_data_received)

    def on_btn_website_clicked(self, widget):
        util.open_website(self.channel.link)

    def on_btnDownloadCover_clicked(self, widget):
        if gpodder.interface == gpodder.GUI:
            dlg = gtk.FileChooserDialog(title=_('Select new podcast cover artwork'), parent=self.gPodderChannel, action=gtk.FILE_CHOOSER_ACTION_OPEN)
            dlg.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
            dlg.add_button(gtk.STOCK_OPEN, gtk.RESPONSE_OK)
        elif gpodder.interface == gpodder.MAEMO:
            dlg = hildon.FileChooserDialog(self.gPodderChannel, gtk.FILE_CHOOSER_ACTION_OPEN)

        if dlg.run() == gtk.RESPONSE_OK:
            url = dlg.get_uri()
            services.cover_downloader.replace_cover(self.channel, url)

        dlg.destroy()

    def on_btnClearCover_clicked(self, widget):
        services.cover_downloader.replace_cover(self.channel)

    def cover_download_finished(self, channel_url, pixbuf):
        if pixbuf is not None:
            self.imgCover.set_from_pixbuf(pixbuf)
        self.gPodderChannel.show()

    def drag_data_received( self, widget, content, x, y, sel, ttype, time):
        files = sel.data.strip().split('\n')
        if len(files) != 1:
            self.show_message( _('You can only drop a single image or URL here.'), _('Drag and drop'))
            return

        file = files[0]

        if file.startswith('file://') or file.startswith('http://'):
            services.cover_downloader.replace_cover(self.channel, file)
            return
        
        self.show_message( _('You can only drop local files and http:// URLs here.'), _('Drag and drop'))

    def on_gPodderChannel_destroy(self, widget, *args):
        services.cover_downloader.unregister('cover-available', self.cover_download_finished)

    def on_btnOK_clicked(self, widget, *args):
        entered_url = self.entryURL.get_text()
        channel_url = self.channel.url

        if entered_url != channel_url:
            if self.show_confirmation(_('Do you really want to move this podcast to <b>%s</b>?') % (saxutils.escape(entered_url),), _('Really change URL?')):
                if hasattr(self, 'callback_change_url'):
                    self.gPodderChannel.hide_all()
                    self.callback_change_url(channel_url, entered_url)

        self.channel.sync_to_devices = not self.cbNoSync.get_active()
        self.channel.device_playlist_name = self.musicPlaylist.get_text()
        self.channel.set_custom_title( self.entryTitle.get_text())
        self.channel.username = self.FeedUsername.get_text().strip()
        self.channel.password = self.FeedPassword.get_text()
        self.channel.save()

        self.gPodderChannel.destroy()
        self.callback_closed()

class gPodderAddPodcastDialog(GladeWidget):
    finger_friendly_widgets = ['btn_close', 'btn_add']

    def new(self):
        if not hasattr(self, 'url_callback'):
            log('No url callback set', sender=self)
            self.url_callback = None
        if hasattr(self, 'custom_label'):
            self.label_add.set_text(self.custom_label)
        if hasattr(self, 'custom_title'):
            self.gPodderAddPodcastDialog.set_title(self.custom_title)
        if gpodder.interface == gpodder.MAEMO:
            self.entry_url.set_text('http://')

    def on_btn_close_clicked(self, widget):
        self.gPodderAddPodcastDialog.destroy()

    def on_entry_url_changed(self, widget):
        self.btn_add.set_sensitive(self.entry_url.get_text().strip() != '')

    def on_btn_add_clicked(self, widget):
        url = self.entry_url.get_text()
        self.on_btn_close_clicked(widget)
        if self.url_callback is not None:
            self.url_callback(url)
        

class gPodderMaemoPreferences(GladeWidget):
    finger_friendly_widgets = ['btn_close', 'label128', 'label129', 'btn_advanced']
    
    def new(self):
        gl.config.connect_gtk_togglebutton('update_on_startup', self.update_on_startup)
        gl.config.connect_gtk_togglebutton('display_tray_icon', self.show_tray_icon)
        gl.config.connect_gtk_togglebutton('enable_notifications', self.show_notifications)
        gl.config.connect_gtk_togglebutton('on_quit_ask', self.on_quit_ask)

        self.restart_required = False
        self.show_tray_icon.connect('clicked', self.on_restart_required)
        self.show_notifications.connect('clicked', self.on_restart_required)

    def on_restart_required(self, widget):
        self.restart_required = True

    def on_btn_advanced_clicked(self, widget):
        self.gPodderMaemoPreferences.destroy()
        gPodderConfigEditor()

    def on_btn_close_clicked(self, widget):
        self.gPodderMaemoPreferences.destroy()
        if self.restart_required:
            self.show_message(_('Please restart gPodder for the changes to take effect.'))


class gPodderProperties(GladeWidget):
    def new(self):
        if not hasattr( self, 'callback_finished'):
            self.callback_finished = None

        if gpodder.interface == gpodder.MAEMO:
            self.table5.hide_all() # player
            self.gPodderProperties.fullscreen()

        gl.config.connect_gtk_editable( 'http_proxy', self.httpProxy)
        gl.config.connect_gtk_editable( 'ftp_proxy', self.ftpProxy)
        gl.config.connect_gtk_editable( 'player', self.openApp)
        gl.config.connect_gtk_editable('videoplayer', self.openVideoApp)
        gl.config.connect_gtk_editable( 'custom_sync_name', self.entryCustomSyncName)
        gl.config.connect_gtk_togglebutton( 'custom_sync_name_enabled', self.cbCustomSyncName)
        gl.config.connect_gtk_togglebutton( 'auto_download_when_minimized', self.downloadnew)
        gl.config.connect_gtk_togglebutton( 'update_on_startup', self.updateonstartup)
        gl.config.connect_gtk_togglebutton( 'only_sync_not_played', self.only_sync_not_played)
        gl.config.connect_gtk_togglebutton( 'fssync_channel_subfolders', self.cbChannelSubfolder)
        gl.config.connect_gtk_togglebutton( 'on_sync_mark_played', self.on_sync_mark_played)
        gl.config.connect_gtk_togglebutton( 'on_sync_delete', self.on_sync_delete)
        gl.config.connect_gtk_togglebutton( 'proxy_use_environment', self.cbEnvironmentVariables)
        gl.config.connect_gtk_spinbutton('episode_old_age', self.episode_old_age)
        gl.config.connect_gtk_togglebutton('auto_remove_old_episodes', self.auto_remove_old_episodes)
        gl.config.connect_gtk_togglebutton('auto_update_feeds', self.auto_update_feeds)
        gl.config.connect_gtk_spinbutton('auto_update_frequency', self.auto_update_frequency)
        gl.config.connect_gtk_togglebutton('display_tray_icon', self.display_tray_icon)
        gl.config.connect_gtk_togglebutton('minimize_to_tray', self.minimize_to_tray)
        gl.config.connect_gtk_togglebutton('enable_notifications', self.enable_notifications)
        gl.config.connect_gtk_togglebutton('start_iconified', self.start_iconified)
        gl.config.connect_gtk_togglebutton('ipod_write_gtkpod_extended', self.ipod_write_gtkpod_extended)
        gl.config.connect_gtk_togglebutton('mp3_player_delete_played', self.delete_episodes_marked_played)
        
        self.enable_notifications.set_sensitive(self.display_tray_icon.get_active())    
        self.minimize_to_tray.set_sensitive(self.display_tray_icon.get_active()) 
        
        self.entryCustomSyncName.set_sensitive( self.cbCustomSyncName.get_active())

        self.iPodMountpoint.set_label( gl.config.ipod_mount)
        self.filesystemMountpoint.set_label( gl.config.mp3_player_folder)
        self.chooserDownloadTo.set_current_folder(gl.downloaddir)

        self.on_sync_delete.set_sensitive(not self.delete_episodes_marked_played.get_active())
        self.on_sync_mark_played.set_sensitive(not self.delete_episodes_marked_played.get_active())
        
        if tagging_supported():
            gl.config.connect_gtk_togglebutton( 'update_tags', self.updatetags)
        else:
            self.updatetags.set_sensitive( False)
            new_label = '%s (%s)' % ( self.updatetags.get_label(), _('needs python-eyed3') )
            self.updatetags.set_label( new_label)

        # device type
        self.comboboxDeviceType.set_active( 0)
        if gl.config.device_type == 'ipod':
            self.comboboxDeviceType.set_active( 1)
        elif gl.config.device_type == 'filesystem':
            self.comboboxDeviceType.set_active( 2)
        elif gl.config.device_type == 'mtp':
            self.comboboxDeviceType.set_active( 3)

        # setup cell renderers
        cellrenderer = gtk.CellRendererPixbuf()
        self.comboAudioPlayerApp.pack_start(cellrenderer, False)
        self.comboAudioPlayerApp.add_attribute(cellrenderer, 'pixbuf', 2)
        cellrenderer = gtk.CellRendererText()
        self.comboAudioPlayerApp.pack_start(cellrenderer, True)
        self.comboAudioPlayerApp.add_attribute(cellrenderer, 'markup', 0)

        cellrenderer = gtk.CellRendererPixbuf()
        self.comboVideoPlayerApp.pack_start(cellrenderer, False)
        self.comboVideoPlayerApp.add_attribute(cellrenderer, 'pixbuf', 2)
        cellrenderer = gtk.CellRendererText()
        self.comboVideoPlayerApp.pack_start(cellrenderer, True)
        self.comboVideoPlayerApp.add_attribute(cellrenderer, 'markup', 0)

        if not hasattr(self, 'user_apps_reader'):
            self.user_apps_reader = UserAppsReader(['audio', 'video'])

        self.comboAudioPlayerApp.set_row_separator_func(self.is_row_separator)
        self.comboVideoPlayerApp.set_row_separator_func(self.is_row_separator)

        if gpodder.interface == gpodder.GUI:
            self.user_apps_reader.read()

        self.comboAudioPlayerApp.set_model(self.user_apps_reader.get_applications_as_model('audio'))
        index = self.find_active_audio_app()
        self.comboAudioPlayerApp.set_active(index)
        self.comboVideoPlayerApp.set_model(self.user_apps_reader.get_applications_as_model('video'))
        index = self.find_active_video_app()
        self.comboVideoPlayerApp.set_active(index)

        self.ipodIcon.set_from_icon_name( 'gnome-dev-ipod', gtk.ICON_SIZE_BUTTON)

    def is_row_separator(self, model, iter):
        return model.get_value(iter, 0) == ''

    def update_mountpoint( self, ipod):
        if ipod is None or ipod.mount_point is None:
            self.iPodMountpoint.set_label( '')
        else:
            self.iPodMountpoint.set_label( ipod.mount_point)

    def find_active_audio_app(self):
        index_custom = -1
        model = self.comboAudioPlayerApp.get_model()
        iter = model.get_iter_first()
        index = 0
        while iter is not None:
            command = model.get_value(iter, 1)
            if command == self.openApp.get_text():
                return index
            if index_custom < 0 and command == '':
                index_custom = index
            iter = model.iter_next(iter)
            index += 1
        # return index of custom command or first item
        return max(0, index_custom)

    def find_active_video_app( self):
        index_custom = -1
        model = self.comboVideoPlayerApp.get_model()
        iter = model.get_iter_first()
        index = 0
        while iter is not None:
            command = model.get_value(iter, 1)
            if command == self.openVideoApp.get_text():
                return index
            if index_custom < 0 and command == '':
                index_custom = index
            iter = model.iter_next(iter)
            index += 1
        # return index of custom command or first item
        return max(0, index_custom)
    
    def set_download_dir( self, new_download_dir, event = None):
        gl.downloaddir = self.chooserDownloadTo.get_filename()
        if gl.downloaddir != self.chooserDownloadTo.get_filename():
            self.notification(_('There has been an error moving your downloads to the specified location. The old download directory will be used instead.'), _('Error moving downloads'))

        if event:
            event.set()
            
    def on_auto_update_feeds_toggled( self, widget, *args):
        self.auto_update_frequency.set_sensitive(widget.get_active())
        
    def on_display_tray_icon_toggled( self, widget, *args):
        self.enable_notifications.set_sensitive(widget.get_active())    
        self.minimize_to_tray.set_sensitive(widget.get_active())    
        
    def on_cbCustomSyncName_toggled( self, widget, *args):
        self.entryCustomSyncName.set_sensitive( widget.get_active())

    def on_only_sync_not_played_toggled( self, widget, *args):
        self.delete_episodes_marked_played.set_sensitive( widget.get_active())
        if not widget.get_active():
            self.delete_episodes_marked_played.set_active(False)

    def on_delete_episodes_marked_played_toggled( self, widget, *args):
        if widget.get_active() and self.only_sync_not_played.get_active():
            self.on_sync_leave.set_active(True)
        self.on_sync_delete.set_sensitive(not widget.get_active())
        self.on_sync_mark_played.set_sensitive(not widget.get_active())

    def on_btnCustomSyncNameHelp_clicked( self, widget):
        examples = [
                '<i>{episode.title}</i> -&gt; <b>Interview with RMS</b>',
                '<i>{episode.basename}</i> -&gt; <b>70908-interview-rms</b>',
                '<i>{episode.published}</i> -&gt; <b>20070908</b>',
                '<i>{podcast.title}</i> -&gt; <b>The Interview Podcast</b>'
        ]

        info = [
                _('You can specify a custom format string for the file names on your MP3 player here.'),
                _('The format string will be used to generate a file name on your device. The file extension (e.g. ".mp3") will be added automatically.'),
                '\n'.join( [ '   %s' % s for s in examples ])
        ]

        self.show_message( '\n\n'.join( info), _('Custom format strings'))

    def on_gPodderProperties_destroy(self, widget, *args):
        self.on_btnOK_clicked( widget, *args)

    def on_btnConfigEditor_clicked(self, widget, *args):
        self.on_btnOK_clicked(widget, *args)
        gPodderConfigEditor()

    def on_comboAudioPlayerApp_changed(self, widget, *args):
        # find out which one
        iter = self.comboAudioPlayerApp.get_active_iter()
        model = self.comboAudioPlayerApp.get_model()
        command = model.get_value( iter, 1)
        if command == '':
            if self.openApp.get_text() == 'default':
                self.openApp.set_text('')
            self.openApp.set_sensitive( True)
            self.openApp.show()
            self.labelCustomCommand.show()
        else:
            self.openApp.set_text( command)
            self.openApp.set_sensitive( False)
            self.openApp.hide()
            self.labelCustomCommand.hide()

    def on_comboVideoPlayerApp_changed(self, widget, *args):
        # find out which one
        iter = self.comboVideoPlayerApp.get_active_iter()
        model = self.comboVideoPlayerApp.get_model()
        command = model.get_value(iter, 1)
        if command == '':
            if self.openVideoApp.get_text() == 'default':
                self.openVideoApp.set_text('')
            self.openVideoApp.set_sensitive(True)
            self.openVideoApp.show()
            self.labelCustomVideoCommand.show()
        else:
            self.openVideoApp.set_text(command)
            self.openVideoApp.set_sensitive(False)
            self.openVideoApp.hide()
            self.labelCustomVideoCommand.hide()

    def on_cbEnvironmentVariables_toggled(self, widget, *args):
         sens = not self.cbEnvironmentVariables.get_active()
         self.httpProxy.set_sensitive( sens)
         self.ftpProxy.set_sensitive( sens)

    def on_comboboxDeviceType_changed(self, widget, *args):
        active_item = self.comboboxDeviceType.get_active()

        # None
        sync_widgets = ( self.only_sync_not_played, self.labelSyncOptions,
                         self.imageSyncOptions, self. separatorSyncOptions,
                         self.on_sync_mark_played, self.on_sync_delete,
                         self.on_sync_leave, self.label_after_sync, self.delete_episodes_marked_played)
        for widget in sync_widgets:
            if active_item == 0:
                widget.hide_all()
            else:
                widget.show_all()

        # iPod
        ipod_widgets = (self.ipodLabel, self.btn_iPodMountpoint,
                        self.ipod_write_gtkpod_extended)
        for widget in ipod_widgets:
            if active_item == 1:
                widget.show_all()
            else:
                widget.hide_all()

        # filesystem-based MP3 player
        fs_widgets = ( self.filesystemLabel, self.btn_filesystemMountpoint,
                       self.cbChannelSubfolder, self.cbCustomSyncName,
                       self.entryCustomSyncName, self.btnCustomSyncNameHelp )
        for widget in fs_widgets:
            if active_item == 2:
                widget.show_all()
            else:
                widget.hide_all()

    def on_btn_iPodMountpoint_clicked(self, widget, *args):
        fs = gtk.FileChooserDialog( title = _('Select iPod mountpoint'), action = gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        fs.add_button( gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        fs.add_button( gtk.STOCK_OPEN, gtk.RESPONSE_OK)
        fs.set_current_folder(self.iPodMountpoint.get_label())
        if fs.run() == gtk.RESPONSE_OK:
            self.iPodMountpoint.set_label( fs.get_filename())
        fs.destroy()

    def on_btn_FilesystemMountpoint_clicked(self, widget, *args):
        fs = gtk.FileChooserDialog( title = _('Select folder for MP3 player'), action = gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        fs.add_button( gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        fs.add_button( gtk.STOCK_OPEN, gtk.RESPONSE_OK)
        fs.set_current_folder(self.filesystemMountpoint.get_label())
        if fs.run() == gtk.RESPONSE_OK:
            self.filesystemMountpoint.set_label( fs.get_filename())
        fs.destroy()

    def on_btnOK_clicked(self, widget, *args):
        gl.config.ipod_mount = self.iPodMountpoint.get_label()
        gl.config.mp3_player_folder = self.filesystemMountpoint.get_label()

        if gl.downloaddir != self.chooserDownloadTo.get_filename():
            new_download_dir = self.chooserDownloadTo.get_filename()
            download_dir_size = util.calculate_size( gl.downloaddir)
            download_dir_size_string = gl.format_filesize( download_dir_size)
            event = Event()

            dlg = gtk.Dialog( _('Moving downloads folder'), self.gPodderProperties)
            dlg.vbox.set_spacing( 5)
            dlg.set_border_width( 5)
         
            label = gtk.Label()
            label.set_line_wrap( True)
            label.set_markup( _('Moving downloads from <b>%s</b> to <b>%s</b>...') % ( saxutils.escape( gl.downloaddir), saxutils.escape( new_download_dir), ))
            myprogressbar = gtk.ProgressBar()
         
            # put it all together
            dlg.vbox.pack_start( label)
            dlg.vbox.pack_end( myprogressbar)

            # switch windows
            dlg.show_all()
            self.gPodderProperties.hide_all()
         
            # hide action area and separator line
            dlg.action_area.hide()
            dlg.set_has_separator( False)

            args = ( new_download_dir, event, )

            thread = Thread( target = self.set_download_dir, args = args)
            thread.start()

            while not event.isSet():
                try:
                    new_download_dir_size = util.calculate_size( new_download_dir)
                except:
                    new_download_dir_size = 0
                if download_dir_size > 0:
                    fract = (1.00*new_download_dir_size) / (1.00*download_dir_size)
                else:
                    fract = 0.0
                if fract < 0.99:
                    myprogressbar.set_text( _('%s of %s') % ( gl.format_filesize( new_download_dir_size), download_dir_size_string, ))
                else:
                    myprogressbar.set_text( _('Finishing... please wait.'))
                myprogressbar.set_fraction(max(0.0,min(1.0,fract)))
                event.wait( 0.1)
                while gtk.events_pending():
                    gtk.main_iteration( False)

            dlg.destroy()

        device_type = self.comboboxDeviceType.get_active()
        if device_type == 0:
            gl.config.device_type = 'none'
        elif device_type == 1:
            gl.config.device_type = 'ipod'
        elif device_type == 2:
            gl.config.device_type = 'filesystem'
        elif device_type == 3:
            gl.config.device_type = 'mtp'
        self.gPodderProperties.destroy()
        if self.callback_finished:
            self.callback_finished()


class gPodderEpisode(GladeWidget):
    finger_friendly_widgets = ['episode_description', 'btnCloseWindow', 'btnDownload', 
    'btnCancel', 'btnPlay', 'btn_website']
    
    def new(self):
        global WEB_BROWSER_ICON
        self.image3166.set_property('icon-name', WEB_BROWSER_ICON)
        services.download_status_manager.register( 'list-changed', self.on_download_status_changed)
        services.download_status_manager.register( 'progress-detail', self.on_download_status_progress)

        self.episode_title.set_markup( '<span weight="bold" size="larger">%s</span>' % saxutils.escape( self.episode.title))

        if gpodder.interface == gpodder.MAEMO:
            # Hide the advanced prefs expander
            self.expander1.hide_all()

        try:
            import gtkhtml2
            document = gtkhtml2.Document()
            document.connect('link-clicked', lambda d, url: util.open_website(url))
            def request_url(document, url, stream):
                stream.write(urllib2.urlopen(url).read())
                stream.close()
            document.connect('request-url', request_url)
            document.clear()
            document.open_stream('text/html')
            document.write_stream('<html><head><meta http-equiv="content-type" content="text/html; charset=utf-8"/></head><body>')
            document.write_stream('<h2>%s</h2><small><em>from <a href="%s">%s</a>, released %s</em></small><br><hr style="border: 1px #eeeeee solid;">' % (saxutils.escape(self.episode.title), self.episode.link, saxutils.escape(self.episode.channel.title), self.episode.cute_pubdate()))
            document.write_stream(self.episode.description)
            document.write_stream('<br><hr style="border: 1px #eeeeee solid;"><p style="font-size: 8px;">%s</p>' % self.episode.link)
            document.write_stream('</body></html>')
            document.close_stream()

            self.episode_title.hide_all()
            self.channel_title.hide_all()
            self.btn_website.hide_all()
            self.expander1.hide_all()

            view = gtkhtml2.View()
            view.set_document(document)
            self.scrolledwindow4.remove(self.scrolledwindow4.get_child())
            self.scrolledwindow4.add(view)
            view.show()
        except ImportError, ie:
            b = gtk.TextBuffer()
            b.set_text(strip(util.remove_html_tags(self.episode.description)))
            self.episode_description.set_buffer( b)

        self.gPodderEpisode.set_title( self.episode.title)
        self.LabelDownloadLink.set_text( self.episode.url)
        self.LabelWebsiteLink.set_text( self.episode.link)
        self.labelPubDate.set_text(self.episode.cute_pubdate())

        # Hide the "Go to website" button if we don't have a valid URL
        if self.episode.link == self.episode.url or not self.episode.link:
            self.btn_website.hide_all()

        self.channel_title.set_markup(_('<i>from %s</i>') % saxutils.escape(self.episode.channel.title))

        self.hide_show_widgets()
        services.download_status_manager.request_progress_detail( self.episode.url)
        gl.config.connect_gtk_window(self.gPodderEpisode, 'episode_window', True)

    def on_btnCancel_clicked( self, widget):
        services.download_status_manager.cancel_by_url( self.episode.url)

    def on_gPodderEpisode_destroy( self, widget):
        services.download_status_manager.unregister( 'list-changed', self.on_download_status_changed)
        services.download_status_manager.unregister( 'progress-detail', self.on_download_status_progress)

    def on_download_status_changed( self):
        self.hide_show_widgets()

    def on_btn_website_clicked(self, widget):
        util.open_website(self.episode.link)

    def on_download_status_progress( self, url, progress, speed):
        if url == self.episode.url:
            progress = float(min(100.0,max(0.0,progress)))
            self.progress_bar.set_fraction(progress/100.0)
            self.progress_bar.set_text( 'Downloading: %d%% (%s)' % ( progress, speed, ))

    def hide_show_widgets( self):
        is_downloading = services.download_status_manager.is_download_in_progress( self.episode.url)
        if is_downloading:
            self.progress_bar.show_all()
            self.btnCancel.show_all()
            self.btnPlay.hide_all()
            self.btnDownload.hide_all()
        else:
            self.progress_bar.hide_all()
            self.btnCancel.hide_all()
            if os.path.exists( self.episode.local_filename()):
                if self.episode.file_type() in ('audio', 'video'):
                    self.btnPlay.set_label(gtk.STOCK_MEDIA_PLAY)
                else:
                    self.btnPlay.set_label(gtk.STOCK_OPEN)
                self.btnPlay.set_use_stock(True)
                self.btnPlay.show_all()
                self.btnDownload.hide_all()
            else:
                self.btnPlay.hide_all()
                self.btnDownload.show_all()

    def on_btnCloseWindow_clicked(self, widget, *args):
        self.gPodderEpisode.destroy()

    def on_btnDownload_clicked(self, widget, *args):
        if self.download_callback:
            self.download_callback()

    def on_btnPlay_clicked(self, widget, *args):
        if self.play_callback:
            self.play_callback()

        self.gPodderEpisode.destroy()


class gPodderSync(GladeWidget):
    def new(self):
        util.idle_add(self.imageSync.set_from_icon_name, 'gnome-dev-ipod', gtk.ICON_SIZE_DIALOG)

        self.device.register('progress', self.on_progress)
        self.device.register('sub-progress', self.on_sub_progress)
        self.device.register('status', self.on_status)
        self.device.register('done', self.on_done)
    
    def on_progress(self, pos, max, text=None):
        if text is None:
            text = _('%d of %d done') % (pos, max)
        util.idle_add(self.progressbar.set_fraction, float(pos)/float(max))
        util.idle_add(self.progressbar.set_text, text)

    def on_sub_progress(self, percentage):
        util.idle_add(self.progressbar.set_text, _('Processing (%d%%)') % (percentage))

    def on_status(self, status):
        util.idle_add(self.status_label.set_markup, '<i>%s</i>' % saxutils.escape(status))

    def on_done(self):
        util.idle_add(self.gPodderSync.destroy)
        if not self.gPodder.minimized:
            util.idle_add(self.notification, _('Your device has been updated by gPodder.'), _('Operation finished'))

    def on_gPodderSync_destroy(self, widget, *args):
        self.device.unregister('progress', self.on_progress)
        self.device.unregister('sub-progress', self.on_sub_progress)
        self.device.unregister('status', self.on_status)
        self.device.unregister('done', self.on_done)
        self.device.cancel()

    def on_cancel_button_clicked(self, widget, *args):
        self.device.cancel()


class gPodderOpmlLister(GladeWidget):
    finger_friendly_widgets = ['btnDownloadOpml', 'btnCancel', 'btnOK', 'treeviewChannelChooser']
    
    def new(self):
        # initiate channels list
        self.channels = []
        self.callback_for_channel = None
        self.callback_finished = None

        if hasattr(self, 'custom_title'):
            self.gPodderOpmlLister.set_title(self.custom_title)
        if hasattr(self, 'hide_url_entry'):
            self.hbox25.hide_all()

        self.setup_treeview(self.treeviewChannelChooser)
        self.setup_treeview(self.treeviewTopPodcastsChooser)
        self.setup_treeview(self.treeviewYouTubeChooser)

        self.notebookChannelAdder.connect('switch-page', lambda a, b, c: self.on_change_tab(c))

    def setup_treeview(self, tv):
        togglecell = gtk.CellRendererToggle()
        togglecell.set_property( 'activatable', True)
        togglecell.connect( 'toggled', self.callback_edited)
        togglecolumn = gtk.TreeViewColumn( '', togglecell, active=0)
        
        titlecell = gtk.CellRendererText()
        titlecell.set_property('ellipsize', pango.ELLIPSIZE_END)
        titlecolumn = gtk.TreeViewColumn(_('Podcast'), titlecell, markup=1)

        for itemcolumn in ( togglecolumn, titlecolumn ):
            tv.append_column(itemcolumn)

    def callback_edited( self, cell, path):
        model = self.get_treeview().get_model()

        url = model[path][2]

        model[path][0] = not model[path][0]
        if model[path][0]:
            self.channels.append( url)
        else:
            self.channels.remove( url)

        self.btnOK.set_sensitive( bool(len(self.get_selected_channels())))

    def get_selected_channels(self, tab=None):
        channels = []

        model = self.get_treeview(tab).get_model()
        if model is not None:
            for row in model:
                if row[0]:
                    channels.append(row[2])

        return channels

    def on_change_tab(self, tab):
        self.btnOK.set_sensitive( bool(len(self.get_selected_channels(tab))))

    def thread_finished(self, model, tab=0):
        if tab == 1:
            tv = self.treeviewTopPodcastsChooser
        elif tab == 2:
            tv = self.treeviewYouTubeChooser
            self.entryYoutubeSearch.set_sensitive(True)
            self.btnSearchYouTube.set_sensitive(True)
            self.btnOK.set_sensitive(False)
        else:
            tv = self.treeviewChannelChooser
            self.btnDownloadOpml.set_sensitive(True)
            self.entryURL.set_sensitive(True)
            self.channels = []

        tv.set_model(model)
        tv.set_sensitive(True)

    def thread_func(self, tab=0):
        if tab == 1:
            model = opml.Importer(gl.config.toplist_url).get_model()
            if len(model) == 0:
                self.notification(_('The specified URL does not provide any valid OPML podcast items.'), _('No feeds found'))
        elif tab == 2:
            model = resolver.find_youtube_channels(self.entryYoutubeSearch.get_text())
            if len(model) == 0:
                self.notification(_('There are no YouTube channels that would match this query.'), _('No channels found'))
        else:
            model = opml.Importer(self.entryURL.get_text()).get_model()
            if len(model) == 0:
                self.notification(_('The specified URL does not provide any valid OPML podcast items.'), _('No feeds found'))

        util.idle_add(self.thread_finished, model, tab)
    
    def get_channels_from_url( self, url, callback_for_channel = None, callback_finished = None):
        if callback_for_channel:
            self.callback_for_channel = callback_for_channel
        if callback_finished:
            self.callback_finished = callback_finished
        self.entryURL.set_text( url)
        self.btnDownloadOpml.set_sensitive( False)
        self.entryURL.set_sensitive( False)
        self.btnOK.set_sensitive( False)
        self.treeviewChannelChooser.set_sensitive( False)
        Thread( target = self.thread_func).start()
        Thread( target = lambda: self.thread_func(1)).start()

    def select_all( self, value ):
        enabled = False
        model = self.get_treeview().get_model()
        if model is not None:
            for row in model:
                row[0] = value
                if value:
                    enabled = True
        self.btnOK.set_sensitive(enabled)

    def on_gPodderOpmlLister_destroy(self, widget, *args):
        pass

    def on_btnDownloadOpml_clicked(self, widget, *args):
        self.get_channels_from_url( self.entryURL.get_text())

    def on_btnSearchYouTube_clicked(self, widget, *args):
        self.entryYoutubeSearch.set_sensitive(False)
        self.treeviewYouTubeChooser.set_sensitive(False)
        self.btnSearchYouTube.set_sensitive(False)
        Thread(target = lambda: self.thread_func(2)).start()

    def on_btnSelectAll_clicked(self, widget, *args):
        self.select_all(True)
    
    def on_btnSelectNone_clicked(self, widget, *args):
        self.select_all(False)

    def on_btnOK_clicked(self, widget, *args):
        self.channels = self.get_selected_channels()
        self.gPodderOpmlLister.destroy()

        # add channels that have been selected
        for url in self.channels:
            if self.callback_for_channel:
                self.callback_for_channel( url)

        if self.callback_finished:
            util.idle_add(self.callback_finished)

    def on_btnCancel_clicked(self, widget, *args):
        self.gPodderOpmlLister.destroy()

    def on_entryYoutubeSearch_key_press_event(self, widget, event):
        if event.keyval == gtk.keysyms.Return:
            self.on_btnSearchYouTube_clicked(widget)

    def get_treeview(self, tab=None):
        if tab is None:
            tab = self.notebookChannelAdder.get_current_page()

        if tab == 0:
            return self.treeviewChannelChooser
        elif tab == 1:
            return self.treeviewTopPodcastsChooser
        else:
            return self.treeviewYouTubeChooser

class gPodderEpisodeSelector( GladeWidget):
    """Episode selection dialog

    Optional keyword arguments that modify the behaviour of this dialog:

      - callback: Function that takes 1 parameter which is a list of
                  the selected episodes (or empty list when none selected)
      - remove_callback: Function that takes 1 parameter which is a list
                         of episodes that should be "removed" (see below)
                         (default is None, which means remove not possible)
      - remove_action: Label for the "remove" action (default is "Remove")
      - remove_finished: Callback after all remove callbacks have finished
                         (default is None, also depends on remove_callback)
      - episodes: List of episodes that are presented for selection
      - selected: (optional) List of boolean variables that define the
                  default checked state for the given episodes
      - selected_default: (optional) The default boolean value for the
                          checked state if no other value is set
                          (default is False)
      - columns: List of (name, sort_name, sort_type, caption) pairs for the
                 columns, the name is the attribute name of the episode to be 
                 read from each episode object.  The sort name is the 
                 attribute name of the episode to be used to sort this column.
                 If the sort_name is None it will use the attribute name for
                 sorting.  The sort type is the type of the sort column.
                 The caption attribute is the text that appear as column caption
                 (default is [('title_and_description', None, None, 'Episode'),])
      - title: (optional) The title of the window + heading
      - instructions: (optional) A one-line text describing what the 
                      user should select / what the selection is for
      - stock_ok_button: (optional) Will replace the "OK" button with
                         another GTK+ stock item to be used for the
                         affirmative button of the dialog (e.g. can 
                         be gtk.STOCK_DELETE when the episodes to be
                         selected will be deleted after closing the 
                         dialog)
      - selection_buttons: (optional) A dictionary with labels as 
                           keys and callbacks as values; for each
                           key a button will be generated, and when
                           the button is clicked, the callback will
                           be called for each episode and the return
                           value of the callback (True or False) will
                           be the new selected state of the episode
      - size_attribute: (optional) The name of an attribute of the 
                        supplied episode objects that can be used to
                        calculate the size of an episode; set this to
                        None if no total size calculation should be
                        done (in cases where total size is useless)
                        (default is 'length')
      - tooltip_attribute: (optional) The name of an attribute of
                           the supplied episode objects that holds
                           the text for the tooltips when hovering
                           over an episode (default is 'description')
                           
    """
    finger_friendly_widgets = ['btnCancel', 'btnOK', 'btnCheckAll', 'btnCheckNone', 'treeviewEpisodes']
    
    COLUMN_INDEX = 0
    COLUMN_TOOLTIP = 1
    COLUMN_TOGGLE = 2
    COLUMN_ADDITIONAL = 3

    def new( self):
        gl.config.connect_gtk_window(self.gPodderEpisodeSelector, 'episode_selector', True)
        if not hasattr( self, 'callback'):
            self.callback = None

        if not hasattr(self, 'remove_callback'):
            self.remove_callback = None

        if not hasattr(self, 'remove_action'):
            self.remove_action = _('Remove')

        if not hasattr(self, 'remove_finished'):
            self.remove_finished = None

        if not hasattr( self, 'episodes'):
            self.episodes = []

        if not hasattr( self, 'size_attribute'):
            self.size_attribute = 'length'

        if not hasattr(self, 'tooltip_attribute'):
            self.tooltip_attribute = 'description'

        if not hasattr( self, 'selection_buttons'):
            self.selection_buttons = {}

        if not hasattr( self, 'selected_default'):
            self.selected_default = False

        if not hasattr( self, 'selected'):
            self.selected = [self.selected_default]*len(self.episodes)

        if len(self.selected) < len(self.episodes):
            self.selected += [self.selected_default]*(len(self.episodes)-len(self.selected))

        if not hasattr( self, 'columns'):
            self.columns = (('title_and_description', None, None, _('Episode')),)

        if hasattr( self, 'title'):
            self.gPodderEpisodeSelector.set_title( self.title)
            self.labelHeading.set_markup( '<b><big>%s</big></b>' % saxutils.escape( self.title))

        if gpodder.interface == gpodder.MAEMO:
            self.labelHeading.hide()

        if hasattr( self, 'instructions'):
            self.labelInstructions.set_text( self.instructions)
            self.labelInstructions.show_all()

        if hasattr(self, 'stock_ok_button'):
            if self.stock_ok_button == 'gpodder-download':
                self.btnOK.set_image(gtk.image_new_from_stock(gtk.STOCK_GO_DOWN, gtk.ICON_SIZE_BUTTON))
                self.btnOK.set_label(_('Download'))
            else:
                self.btnOK.set_label(self.stock_ok_button)
                self.btnOK.set_use_stock(True)

        # check/uncheck column
        toggle_cell = gtk.CellRendererToggle()
        toggle_cell.connect( 'toggled', self.toggle_cell_handler)
        self.treeviewEpisodes.append_column( gtk.TreeViewColumn( '', toggle_cell, active=self.COLUMN_TOGGLE))
        
        next_column = self.COLUMN_ADDITIONAL
        for name, sort_name, sort_type, caption in self.columns:
            renderer = gtk.CellRendererText()
            renderer.set_property( 'ellipsize', pango.ELLIPSIZE_END)
            column = gtk.TreeViewColumn(caption, renderer, markup=next_column)
            column.set_resizable( True)
            # Only set "expand" on the first column (so more text is displayed there)
            column.set_expand(next_column == self.COLUMN_ADDITIONAL)
            if sort_name is not None:
                column.set_sort_column_id(next_column+1)
            else:
                column.set_sort_column_id(next_column)
            self.treeviewEpisodes.append_column( column)
            next_column += 1
            
            if sort_name is not None:
                # add the sort column
                column = gtk.TreeViewColumn()
                column.set_visible(False)
                self.treeviewEpisodes.append_column( column)
                next_column += 1

        column_types = [ gobject.TYPE_INT, gobject.TYPE_STRING, gobject.TYPE_BOOLEAN ]
        # add string column type plus sort column type if it exists
        for name, sort_name, sort_type, caption in self.columns:
            column_types.append(gobject.TYPE_STRING)
            if sort_name is not None:
                column_types.append(sort_type)
        self.model = gtk.ListStore( *column_types)

        tooltip = None
        for index, episode in enumerate( self.episodes):
            if self.tooltip_attribute is not None:
                try:
                    tooltip = getattr(episode, self.tooltip_attribute)
                except:
                    log('Episode object %s does not have tooltip attribute: "%s"', episode, self.tooltip_attribute, sender=self)
                    tooltip = None
            row = [ index, tooltip, self.selected[index] ]
            for name, sort_name, sort_type, caption in self.columns:
                if not hasattr(episode, name):
                    log('Warning: Missing attribute "%s"', name, sender=self)
                    row.append(None)
                else:
                    row.append(getattr( episode, name))
                    
                if sort_name is not None:
                    if not hasattr(episode, sort_name):
                        log('Warning: Missing attribute "%s"', sort_name, sender=self)
                        row.append(None)
                    else:
                        row.append(getattr( episode, sort_name))
            self.model.append( row)

        if self.remove_callback is not None:
            self.btnRemoveAction.show()
            self.btnRemoveAction.set_label(self.remove_action)

        # connect to tooltip signals
        if self.tooltip_attribute is not None:
            try:
                self.treeviewEpisodes.set_property('has-tooltip', True)
                self.treeviewEpisodes.connect('query-tooltip', self.treeview_episodes_query_tooltip)
            except:
                log('I cannot set has-tooltip/query-tooltip (need at least PyGTK 2.12)', sender=self)
        self.last_tooltip_episode = None
        self.episode_list_can_tooltip = True

        self.treeviewEpisodes.connect('button-press-event', self.treeview_episodes_button_pressed)
        self.treeviewEpisodes.set_rules_hint( True)
        self.treeviewEpisodes.set_model( self.model)
        self.treeviewEpisodes.columns_autosize()
        self.calculate_total_size()

    def treeview_episodes_query_tooltip(self, treeview, x, y, keyboard_tooltip, tooltip):
        # With get_bin_window, we get the window that contains the rows without
        # the header. The Y coordinate of this window will be the height of the
        # treeview header. This is the amount we have to subtract from the
        # event's Y coordinate to get the coordinate to pass to get_path_at_pos
        (x_bin, y_bin) = treeview.get_bin_window().get_position()
        y -= x_bin
        y -= y_bin
        (path, column, rx, ry) = treeview.get_path_at_pos(x, y) or (None,)*4

        if not self.episode_list_can_tooltip:
            self.last_tooltip_episode = None
            return False

        if path is not None:
            model = treeview.get_model()
            iter = model.get_iter(path)
            index = model.get_value(iter, self.COLUMN_INDEX)
            description = model.get_value(iter, self.COLUMN_TOOLTIP)
            if self.last_tooltip_episode is not None and self.last_tooltip_episode != index:
                self.last_tooltip_episode = None
                return False
            self.last_tooltip_episode = index

            if description is not None:
                tooltip.set_text(description)
                return True
            else:
                return False

        self.last_tooltip_episode = None
        return False

    def treeview_episodes_button_pressed(self, treeview, event):
        if event.button == 3:
            menu = gtk.Menu()

            if len(self.selection_buttons):
                for label in self.selection_buttons:
                    item = gtk.MenuItem(label)
                    item.connect('activate', self.custom_selection_button_clicked, label)
                    menu.append(item)
                menu.append(gtk.SeparatorMenuItem())

            item = gtk.MenuItem(_('Select all'))
            item.connect('activate', self.on_btnCheckAll_clicked)
            menu.append(item)

            item = gtk.MenuItem(_('Select none'))
            item.connect('activate', self.on_btnCheckNone_clicked)
            menu.append(item)

            menu.show_all()
            # Disable tooltips while we are showing the menu, so 
            # the tooltip will not appear over the menu
            self.episode_list_can_tooltip = False
            menu.connect('deactivate', lambda menushell: self.episode_list_allow_tooltips())
            menu.popup(None, None, None, event.button, event.time)

            return True

    def episode_list_allow_tooltips(self):
        self.episode_list_can_tooltip = True

    def calculate_total_size( self):
        if self.size_attribute is not None:
            (total_size, count) = (0, 0)
            for episode in self.get_selected_episodes():
                try:
                    total_size += int(getattr( episode, self.size_attribute))
                    count += 1
                except:
                    log( 'Cannot get size for %s', episode.title, sender = self)

            text = []
            if count == 0: 
                text.append(_('Nothing selected'))
            elif count == 1:
                text.append(_('One episode selected'))
            else:
                text.append(_('%d episodes selected') % count)
            if total_size > 0: 
                text.append(_('total size: %s') % gl.format_filesize(total_size))
            self.labelTotalSize.set_text(', '.join(text))
            self.btnOK.set_sensitive(count>0)
            self.btnRemoveAction.set_sensitive(count>0)
            if count > 0:
                self.btnCancel.set_label(gtk.STOCK_CANCEL)
            else:
                self.btnCancel.set_label(gtk.STOCK_CLOSE)
        else:
            self.btnOK.set_sensitive(False)
            self.btnRemoveAction.set_sensitive(False)
            for index, row in enumerate(self.model):
                if self.model.get_value(row.iter, self.COLUMN_TOGGLE) == True:
                    self.btnOK.set_sensitive(True)
                    self.btnRemoveAction.set_sensitive(True)
                    break
            self.labelTotalSize.set_text('')

    def toggle_cell_handler( self, cell, path):
        model = self.treeviewEpisodes.get_model()
        model[path][self.COLUMN_TOGGLE] = not model[path][self.COLUMN_TOGGLE]

        self.calculate_total_size()

    def custom_selection_button_clicked(self, button, label):
        callback = self.selection_buttons[label]

        for index, row in enumerate( self.model):
            new_value = callback( self.episodes[index])
            self.model.set_value( row.iter, self.COLUMN_TOGGLE, new_value)

        self.calculate_total_size()

    def on_btnCheckAll_clicked( self, widget):
        for row in self.model:
            self.model.set_value( row.iter, self.COLUMN_TOGGLE, True)

        self.calculate_total_size()

    def on_btnCheckNone_clicked( self, widget):
        for row in self.model:
            self.model.set_value( row.iter, self.COLUMN_TOGGLE, False)

        self.calculate_total_size()

    def on_remove_action_activate(self, widget):
        episodes = self.get_selected_episodes(remove_episodes=True)

        for episode in episodes:
            self.remove_callback(episode)

        if self.remove_finished is not None:
            self.remove_finished()
        self.calculate_total_size()

    def get_selected_episodes( self, remove_episodes=False):
        selected_episodes = []

        for index, row in enumerate( self.model):
            if self.model.get_value( row.iter, self.COLUMN_TOGGLE) == True:
                selected_episodes.append( self.episodes[self.model.get_value( row.iter, self.COLUMN_INDEX)])

        if remove_episodes:
            for episode in selected_episodes:
                index = self.episodes.index(episode)
                iter = self.model.get_iter_first()
                while iter is not None:
                    if self.model.get_value(iter, self.COLUMN_INDEX) == index:
                        self.model.remove(iter)
                        break
                    iter = self.model.iter_next(iter)

        return selected_episodes

    def on_btnOK_clicked( self, widget):
        self.gPodderEpisodeSelector.destroy()
        if self.callback is not None:
            self.callback( self.get_selected_episodes())

    def on_btnCancel_clicked( self, widget):
        self.gPodderEpisodeSelector.destroy()
        if self.callback is not None:
            self.callback([])

class gPodderConfigEditor(GladeWidget):
    finger_friendly_widgets = ['btnShowAll', 'btnClose', 'configeditor']
    
    def new(self):
        name_column = gtk.TreeViewColumn(_('Setting'))
        name_renderer = gtk.CellRendererText()
        name_column.pack_start(name_renderer)
        name_column.add_attribute(name_renderer, 'text', 0)
        name_column.add_attribute(name_renderer, 'style', 5)
        self.configeditor.append_column(name_column)

        value_column = gtk.TreeViewColumn(_('Set to'))
        value_check_renderer = gtk.CellRendererToggle()
        value_column.pack_start(value_check_renderer, expand=False)
        value_column.add_attribute(value_check_renderer, 'active', 7)
        value_column.add_attribute(value_check_renderer, 'visible', 6)
        value_column.add_attribute(value_check_renderer, 'activatable', 6)
        value_check_renderer.connect('toggled', self.value_toggled)

        value_renderer = gtk.CellRendererText()
        value_column.pack_start(value_renderer)
        value_column.add_attribute(value_renderer, 'text', 2)
        value_column.add_attribute(value_renderer, 'visible', 4)
        value_column.add_attribute(value_renderer, 'editable', 4)
        value_column.add_attribute(value_renderer, 'style', 5)
        value_renderer.connect('edited', self.value_edited)
        self.configeditor.append_column(value_column)

        self.model = gl.config.model()
        self.filter = self.model.filter_new()
        self.filter.set_visible_func(self.visible_func)

        self.configeditor.set_model(self.filter)
        self.configeditor.set_rules_hint(True)

    def visible_func(self, model, iter, user_data=None):
        text = self.entryFilter.get_text().lower()
        if text == '':
            return True
        else:
            # either the variable name or its value
            return (text in model.get_value(iter, 0).lower() or
                    text in model.get_value(iter, 2).lower())

    def value_edited(self, renderer, path, new_text):
        model = self.configeditor.get_model()
        iter = model.get_iter(path)
        name = model.get_value(iter, 0)
        type_cute = model.get_value(iter, 1)

        if not gl.config.update_field(name, new_text):
            self.notification(_('Cannot set value of <b>%s</b> to <i>%s</i>.\n\nNeeded data type: %s') % (saxutils.escape(name), saxutils.escape(new_text), saxutils.escape(type_cute)), _('Error updating %s') % saxutils.escape(name))
    
    def value_toggled(self, renderer, path):
        model = self.configeditor.get_model()
        iter = model.get_iter(path)
        field_name = model.get_value(iter, 0)
        field_type = model.get_value(iter, 3)

        # Flip the boolean config flag
        if field_type == bool:
            gl.config.toggle_flag(field_name)
    
    def on_entryFilter_changed(self, widget):
        self.filter.refilter()

    def on_btnShowAll_clicked(self, widget):
        self.entryFilter.set_text('')
        self.entryFilter.grab_focus()

    def on_btnClose_clicked(self, widget):
        self.gPodderConfigEditor.destroy()

class gPodderPlaylist(GladeWidget):
    finger_friendly_widgets = ['btnCancelPlaylist', 'btnSavePlaylist', 'treeviewPlaylist']

    def new(self):
        self.m3u_header = '#EXTM3U\n'
        self.mountpoint = util.find_mount_point(gl.config.mp3_player_folder)
        if self.mountpoint == '/':
            self.mountpoint = gl.config.mp3_player_folder
            log('Warning: MP3 player resides on / - using %s as MP3 player root', self.mountpoint, sender=self)
        self.playlist_file = os.path.join(self.mountpoint,
                                          gl.config.mp3_player_playlist_file)
        icon_theme = gtk.icon_theme_get_default()
        self.icon_new = icon_theme.load_icon(gtk.STOCK_NEW, 16, 0)

        # add column two
        check_cell = gtk.CellRendererToggle()
        check_cell.set_property('activatable', True)
        check_cell.connect('toggled', self.cell_toggled)
        check_column = gtk.TreeViewColumn(_('Use'), check_cell, active=1)
        self.treeviewPlaylist.append_column(check_column)

        # add column three
        column = gtk.TreeViewColumn(_('Filename'))
        icon_cell = gtk.CellRendererPixbuf()
        column.pack_start(icon_cell, False)
        column.add_attribute(icon_cell, 'pixbuf', 0)
        filename_cell = gtk.CellRendererText()
        column.pack_start(filename_cell, True)
        column.add_attribute(filename_cell, 'text', 2)

        column.set_resizable(True)
        self.treeviewPlaylist.append_column(column)

        # Make treeview reorderable
        self.treeviewPlaylist.set_reorderable(True)

        # init liststore
        self.playlist = gtk.ListStore(gtk.gdk.Pixbuf, bool, str)
        self.treeviewPlaylist.set_model(self.playlist)

        # read device and playlist and fill the TreeView
        self.m3u = self.read_m3u()
        self.device = self.read_device()
        self.write2gui()

    def cell_toggled(self, cellrenderertoggle, path):
        (treeview, liststore) = (self.treeviewPlaylist, self.playlist)
        it = liststore.get_iter(path)
        liststore.set_value(it, 1, not liststore.get_value(it, 1))

    def on_btnCancelPlaylist_clicked(self, widget):
        self.gPodderPlaylist.destroy()

    def on_btnSavePlaylist_clicked(self, widget):
        self.write_m3u()
        self.gPodderPlaylist.destroy()

    def read_m3u(self):
        """
        read all files from the existing playlist
        """
        tracks = []
        if os.path.exists(self.playlist_file):
            for line in open(self.playlist_file, 'r'):
                if line != self.m3u_header:
                    if line.startswith('#'):
                        tracks.append([False, line[1:].strip()])
                    else:
                        tracks.append([True, line.strip()])
        return tracks

    def write_m3u(self):
        """
        write the list into the playlist on the device
        """
        playlist_folder = os.path.split(self.playlist_file)[0]
        if not util.make_directory(playlist_folder):
            self.show_message(_('Folder %s could not be created.') % playlist_folder, _('Error writing playlist'))
        else:
            try:
                fp = open(self.playlist_file, 'w')
                fp.write(self.m3u_header)
                for icon, checked, filename in self.playlist:
                    if not checked:
                        fp.write('#')
                    fp.write(filename)
                    fp.write('\n')
                fp.close()
                self.show_message(_('The playlist on your MP3 player has been updated.'), _('Update successful'))
            except IOError, ioe:
                self.show_message(str(ioe), _('Error writing playlist file'))

    def read_device(self):
        """
        read all files from the device
        """
        tracks = []
        for root, dirs, files in os.walk(gl.config.mp3_player_folder):
            for file in files:
                filename = os.path.join(root, file)

                if filename == self.playlist_file:
                    # We don't want to have our playlist file as
                    # an entry in our file list, so skip it!
                    break

                if not gl.config.mp3_player_playlist_absolute_path:
                    filename = filename[len(self.mountpoint):]

                if gl.config.mp3_player_playlist_win_path:
                    filename = filename.replace( '/', '\\')

                tracks.append(filename)
        return tracks

    def write2gui(self):
        # add the files from the device to the list only when
        # they are not yet in the playlist
        # mark this files as NEW
        for filename in self.device[:]:
            m3ulist = [file[1] for file in self.m3u]
            if filename not in m3ulist:
                self.playlist.append([self.icon_new, False, filename])

        # add the files from the playlist to the list only when
        # they are on the device
        for checked, filename in self.m3u[:]:
            if filename in self.device:
                self.playlist.append([None, checked, filename])

class gPodderDependencyManager(GladeWidget):
    def new(self):
        col_name = gtk.TreeViewColumn(_('Feature'), gtk.CellRendererText(), text=0)
        self.treeview_components.append_column(col_name)
        col_installed = gtk.TreeViewColumn(_('Status'), gtk.CellRendererText(), text=2)
        self.treeview_components.append_column(col_installed)
        self.treeview_components.set_model(services.dependency_manager.get_model())
        self.btn_about.set_sensitive(False)

    def on_btn_about_clicked(self, widget):
        selection = self.treeview_components.get_selection()
        model, iter = selection.get_selected()
        if iter is not None:
            title = model.get_value(iter, 0)
            description = model.get_value(iter, 1)
            available = model.get_value(iter, 3)
            missing = model.get_value(iter, 4)

            if not available:
                description += '\n\n'+_('Missing components:')+'\n\n'+missing

            self.show_message(description, title)

    def on_btn_install_clicked(self, widget):
        # TODO: Implement package manager integration
        pass

    def on_treeview_components_cursor_changed(self, treeview):
        self.btn_about.set_sensitive(treeview.get_selection().count_selected_rows() > 0)
        # TODO: If installing is possible, enable btn_install

    def on_gPodderDependencyManager_response(self, dialog, response_id):
        self.gPodderDependencyManager.destroy()

class gPodderWelcome(GladeWidget):
    finger_friendly_widgets = ['btnOPML', 'btnMygPodder', 'btnCancel']

    def new(self):
        pass

    def on_show_example_podcasts(self, button):
        self.gPodderWelcome.destroy()
        self.show_example_podcasts_callback(None)

    def on_setup_my_gpodder(self, gpodder):
        self.gPodderWelcome.destroy()
        self.setup_my_gpodder_callback(None)

    def on_btnCancel_clicked(self, button):
        self.gPodderWelcome.destroy()

def main():
    gobject.threads_init()
    gtk.window_set_default_icon_name( 'gpodder')

    gPodder().run()



