#!/usr/bin/env python
# Copyright (c) 2010 Pablo Seminario <pabluk@gmail.com>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import gtk
import pygtk
pygtk.require('2.0')
import pango
import threading
import sys
import evdev
import time
from devices import InputFinder
import modmap
import appindicator

gtk.gdk.threads_init()

APP_NAME = 'Screenkey'
APP_DESC = 'Screencast your keys'
APP_URL = 'http://launchpad.net/screenkey'
VERSION = '0.1'
AUTHOR = 'Pablo Seminario'

REPLACE_KEYS = {
	1:u'Esc ',
	15:u'\u21B9 ',
	28:u'\u23CE ',
	57:u' ',
	58:u'Caps ',
	59:u'F1 ', 
	60:u'F2 ', 
	61:u'F3 ', 
	62:u'F4 ', 
	63:u'F5 ', 
	64:u'F6 ', 
	65:u'F7 ', 
	66:u'F8 ', 
	67:u'F9 ', 
	68:u'F10 ', 
	87:u'F11 ', 
	88:u'F12 ', 
	102:u'Home ',
	103:u'\u2191',
	104:u'PgUp ',
	105:u'\u2190',
	106:u'\u2192',
	107:u'End ',
	108:u'\u2193',
	109:u'PgDn ',
	110:u'Ins ',
	111:u'Del ',
	127:u'',
}

class Screenkey(threading.Thread):

	stopthread = threading.Event()

	def __init__(self, *args):
		threading.Thread.__init__(self)

		finder = InputFinder()
		finder.connect('keyboard-found', self.DeviceFound)
		finder.connect('keyboard-lost', self.DeviceLost)

		try:
			nodes = [x.block for x in finder.keyboards.values()]
			self.devices = evdev.DeviceGroup(nodes)
		except OSError, e:
			print
			print 'You may need to run this as %r' % 'sudo %s' % sys.argv[0]
			sys.exit(-1)

		self.keymap = modmap.get_keymap_table()
		self.modifiers = modmap.get_modifier_map()

		self.ind = appindicator.Indicator(
				"screenkey", "indicator-messages", 
				appindicator.CATEGORY_APPLICATION_STATUS)
		self.ind.set_status(appindicator.STATUS_ACTIVE)
		self.ind.set_attention_icon("indicator-messages-new")
		self.ind.set_icon("gtk-bold")

		menu = gtk.Menu()
		about_item = gtk.ImageMenuItem(gtk.STOCK_ABOUT)
		about_item.connect("activate", self.about_dialog)
		about_item.show()
		separator_item = gtk.SeparatorMenuItem()
		separator_item.show()
		quit_item = gtk.ImageMenuItem(gtk.STOCK_QUIT)
		quit_item.connect("activate", self.quit)
		quit_item.show()
		menu.append(about_item)
		menu.append(separator_item)
		menu.append(quit_item)
		menu.show()

		self.ind.set_menu(menu)

		self.window = gtk.Window()
		self.window.set_name(APP_NAME)

		self.text = ""
		self.timer = None
		self.command = None
		self.shift = None
		self.cmd_keys = {
			'shift': False,
			'ctrl': False,
			'alt': False,
			'capslock': False,
			'meta': False,
			'super':False
			}

		screen_width = gtk.gdk.screen_width()	
		screen_height = gtk.gdk.screen_height()	

		window_width = screen_width
		# We use a percentage of the screen
		window_height = 10 * screen_height / 100

		self.window.set_skip_taskbar_hint(True)
		self.window.set_skip_pager_hint(True)
		self.window.set_keep_below(True)
		self.window.set_decorated(False)
		self.window.stick()
		self.window.set_property('accept-focus', False)
		self.window.set_property('focus-on-map', False)
		self.window.set_position(gtk.WIN_POS_CENTER)
		self.window.set_default_size(window_width, window_height)
		bgcolor = gtk.gdk.color_parse("black")
		self.window.modify_bg(gtk.STATE_NORMAL, bgcolor)
		self.window.set_opacity(0.0)

		self.window.set_gravity(gtk.gdk.GRAVITY_CENTER)

		self.window.move(0, screen_height - window_height * 2)

		self.window.connect("delete_event", lambda w,e: gtk.main_quit())

		self.label = gtk.Label()
		self.label.set_use_markup(True)
		self.label.set_justify(gtk.JUSTIFY_RIGHT)
		self.label.set_ellipsize(pango.ELLIPSIZE_START)
		self.window.add(self.label)
		self.window.show_all()

	def show_indicator(self):
		self.window.set_opacity(0.7)
		self.window.set_keep_above(True)

	def hide_indicator(self):
		self.text = ""
		self.update_text()
		self.window.set_opacity(0.0)
		self.window.set_keep_below(True)
		self.timer = None

	def update_text(self, string=None):
		if not string is None:
			self.label.set_markup("<span font='Sans Bold 28'>"
				"<span color='#777'>%s</span>"
				"<span color='#fff'>%s</span></span>"
				% (self.text, string))
			self.text = "%s%s" % (self.text, string)
		else:
			self.label.set_markup("")
		

	def key_press(self, event):
		code_num = event.codeMaps[event.type].toNumber(event.code)
		if code_num in self.keymap:
		  	key_normal, key_shift, key_dead, key_deadshift = self.keymap[code_num]
		else:
		  	print 'No mapping for scan_code %d' % code_num
			return

		key = ''
		mod = ''
		# Alt key
		if code_num in self.modifiers['mod1']:
			if event.value in (1, 2):
				self.cmd_keys['alt'] = True
			else:
				self.cmd_keys['alt'] = False
			return
		# Meta key 
		# Fixme: we must use self.modifiers['mod5']
		#        but doesn't work
		if code_num == 100:
			if event.value in (1, 2):
				self.cmd_keys['meta'] = True
			else:
				self.cmd_keys['meta'] = False
			return
		# Super key 
		if code_num in self.modifiers['mod4']:
			if event.value in (1, 2):
				self.cmd_keys['super'] = True
			else:
				self.cmd_keys['super'] = False
			return
		# Ctrl keys
		elif code_num in self.modifiers['control']:
			if event.value in (1, 2):
				self.cmd_keys['ctrl'] = True
			else:
				self.cmd_keys['ctrl'] = False
			return
		# Shift keys
		elif code_num in self.modifiers['shift']:
			if event.value in (1,2):
				self.cmd_keys['shift'] = True
			else:
				self.cmd_keys['shift'] = False
			return
		# Capslock key
		elif code_num in self.modifiers['lock']:
			if event.value == 1:
				if self.cmd_keys['capslock']:
					self.cmd_keys['capslock'] = False
				else:
					self.cmd_keys['capslock'] = True
			return
		# Backspace key
		elif code_num == 14 and event.value == 1:
			self.text = self.text[:-1]
			key = ""
		else:
			if event.value == 1:
				key = key_normal
				if self.cmd_keys['ctrl']:
					mod = mod + "Ctrl+"
				if self.cmd_keys['alt']:
					mod = mod + "Alt+"
				if self.cmd_keys['super']:
					mod = mod + "Super+"

				if self.cmd_keys['shift']:
					key = key_shift
				if self.cmd_keys['capslock'] and ord(key_normal) in range(97,123):
					key = key_shift
				if self.cmd_keys['meta']:
					key = key_dead
				if self.cmd_keys['shift'] and self.cmd_keys['meta']:
					key = key_deadshift

				if code_num in REPLACE_KEYS:
					key = REPLACE_KEYS[code_num]

				if mod != '':
					key = "%s%s " % (mod, key)
				else:
					key = "%s%s" % (mod, key)
			else:
				return
		self.show_indicator()
		print "Debug: %s %s --" % (key, code_num)
		self.update_text(key)
		if self.timer:
			self.timer.cancel()

		self.timer = threading.Timer(2.5, self.hide_indicator)
		self.timer.start()

	def about_dialog(self, widget, data=None):
		about = gtk.AboutDialog()
		about.set_program_name(APP_NAME)
		about.set_version(VERSION)
		about.set_copyright(u"2010 \u00a9 %s" % AUTHOR)
		about.set_comments(APP_DESC)
		about.set_website(APP_URL)
		about.set_icon_name('preferences-desktop-keyboard-shortcuts')
		about.set_logo_icon_name('preferences-desktop-keyboard-shortcuts')
		about.run()
		about.destroy()

	def quit(self, widget, data=None):
		self.stopthread.set()
		gtk.main_quit()

	def DeviceFound(self, finder, device):
		dev = evdev.Device(device.block)
		self.devices.devices.append(dev)
		self.devices.fds.append(dev.fd)
      
	def DeviceLost(self, finder, device):
		dev = None
		for x in self.devices.devices:
			if x.filename == device.block:
				dev = x
				break
      
		if dev:
			self.devices.fds.remove(dev.fd)
			self.devices.devices.remove(dev)
      
	def run(self):
		while not self.stopthread.isSet():
			event = self.devices.next_event()
			if event is not None:
				if event.type == "EV_KEY":
					if event.code.startswith("KEY"):
						self.key_press(event)
def Main():
	s = Screenkey()
	s.start()
	gtk.main()



if __name__ == "__main__":
	Main()

