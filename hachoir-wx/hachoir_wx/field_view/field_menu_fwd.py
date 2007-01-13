# -*- coding: utf-8 -*-

import wx, wx.xrc

class field_menu_fwd_t:
    def __init__(self, imp):
        self.imp = imp

    def on_field_view_ready(self, dispatcher, view):
        assert view is not None

        view.Bind(wx.EVT_MENU, self.on_addr_rel,
          id = wx.xrc.XRCID('field_menu_address_relative'))
        view.Bind(wx.EVT_MENU, self.on_addr_abs,
          id = wx.xrc.XRCID('field_menu_address_absolute'))
        view.Bind(wx.EVT_MENU, self.on_addr_hex,
          id = wx.xrc.XRCID('field_menu_address_base_hex'))
        view.Bind(wx.EVT_MENU, self.on_addr_dec,
          id = wx.xrc.XRCID('field_menu_address_base_dec'))
        view.Bind(wx.EVT_MENU, self.on_dump_to_disk,
          id = wx.xrc.XRCID('field_menu_dump_to_disk'))

    def on_addr_rel(self, event):
        self.imp.on_addr_rel()

    def on_addr_abs(self, event):
        self.imp.on_addr_abs()

    def on_addr_hex(self, event):
        self.imp.on_addr_hex()

    def on_addr_dec(self, event):
        self.imp.on_addr_dec()

    def on_dump_to_disk(self, event):
        self.imp.on_dump_to_disk()