"""Native, keyboard-accessible dialogs using Windows system colours."""
import wx

from .settings import Options


def heading(parent, text):
    label = wx.StaticText(parent, label=text)
    font = label.GetFont()
    font.SetPointSize(16)
    font.SetWeight(wx.FONTWEIGHT_BOLD)
    label.SetFont(font)
    return label


class ResultDialog(wx.Dialog):
    def __init__(self, parent, target, on_retry, on_close, on_copy):
        super().__init__(parent, title="Drishya — " + target,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.on_retry, self.on_close, self.on_copy = on_retry, on_close, on_copy
        self.can_retry = True
        self.text = ""
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(heading(self, "Drishya"), 0, wx.ALL, 16)
        self.status = wx.StaticText(self, label="Describing " + target.lower() + " locally…")
        box.Add(self.status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        box.Add(wx.StaticText(self, label="&Description"), 0, wx.LEFT | wx.RIGHT, 16)
        self.description = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        self.description.SetMinSize((520, 220))
        box.Add(self.description, 1, wx.EXPAND | wx.ALL, 16)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.copyButton = wx.Button(self, label="&Copy")
        self.retryButton = wx.Button(self, label="&Retry")
        self.closeButton = wx.Button(self, wx.ID_CANCEL, label="&Cancel")
        for button in (self.copyButton, self.retryButton, self.closeButton):
            buttons.Add(button, 0, wx.LEFT, 8)
        box.Add(buttons, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 16)
        self.SetSizerAndFit(box)
        self.SetMinSize((560, 360))
        self.copyButton.Disable()
        self.retryButton.Disable()
        self.copyButton.Bind(wx.EVT_BUTTON, lambda event: self.on_copy(self.text))
        self.retryButton.Bind(wx.EVT_BUTTON, lambda event: self.on_retry())
        self.closeButton.Bind(wx.EVT_BUTTON, lambda event: self.on_close())
        self.Bind(wx.EVT_CLOSE, lambda event: self.on_close())
        self.closeButton.SetDefault()
        self.CentreOnScreen()

    def focus_initial(self):
        (self.copyButton if self.copyButton.IsEnabled() else self.closeButton).SetFocus()

    def set_pending(self):
        self.text = ""
        self.description.ChangeValue("")
        self.status.SetLabel("Describing locally… Press Cancel to stop.")
        self.copyButton.Disable()
        self.retryButton.Disable()
        self.closeButton.SetLabel("&Cancel")
        self.closeButton.SetFocus()

    def show_result(self, text, model, seconds):
        self.text = text
        self.description.ChangeValue(text)
        self.status.SetLabel(f"{model} · {seconds:.1f} seconds · Local description")
        self.copyButton.Enable()
        self.retryButton.Enable(self.can_retry)
        self.closeButton.SetLabel("&Close")
        self.copyButton.SetDefault()
        self.copyButton.SetFocus()
        self.Layout()

    def show_error(self, error):
        self.text = ""
        self.description.ChangeValue(str(error))
        self.status.SetLabel("Description unavailable")
        self.copyButton.Disable()
        self.retryButton.Enable(self.can_retry)
        self.closeButton.SetLabel("&Close")
        self.description.SetFocus()
        self.Layout()


class SettingsDialog(wx.Dialog):
    def __init__(self, parent, options, on_save, on_setup, ready):
        super().__init__(parent, title="Drishya settings", style=wx.DEFAULT_DIALOG_STYLE)
        self.on_save, self.on_setup = on_save, on_setup
        self.on_close = self.Destroy
        self._setting_up = False
        self._sizes = [512, 768, 1024, 1536]
        if options.max_side not in self._sizes:
            self._sizes.append(options.max_side)
            self._sizes.sort()
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(heading(self, "Make Drishya yours"), 0, wx.ALL, 16)
        box.Add(wx.StaticText(self, label="Local descriptions. Your images stay on this computer."),
                0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        grid = wx.FlexGridSizer(cols=2, vgap=12, hgap=16)
        grid.AddGrowableCol(1)

        def field(label, control_class, **kwargs):
            # Windows associates a control with the preceding native label.
            static = wx.StaticText(self, label=label)
            control = control_class(self, **kwargs)
            grid.Add(static, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(control, 1, wx.EXPAND)
            return control

        box.Add(wx.StaticText(self, label="Image description model: SmolVLM2 500M"),
                0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        self.detail = field("Description &detail", wx.Choice, choices=["Concise", "Detailed"])
        self.detail.SetSelection(0 if options.detail == "concise" else 1)
        self.size = field("Maximum &image size", wx.Choice, choices=[f"{size} pixels" for size in self._sizes])
        self.size.SetSelection(self._sizes.index(options.max_side))
        self.threads = field("CPU &threads", wx.SpinCtrl, min=1, max=12, initial=options.threads)
        box.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        self.speak = wx.CheckBox(self, label="&Read descriptions aloud automatically")
        self.speak.SetValue(options.speak)
        box.Add(self.speak, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        self.status = wx.StaticText(self, label="Model installed. Ready offline." if ready() else "Model not installed. Download it once to get started.")
        box.Add(self.status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        self.progress = wx.Gauge(self, range=100)
        box.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.setupButton = wx.Button(self, label="Download / verify &model")
        self.saveButton = wx.Button(self, wx.ID_OK, label="&Save")
        self.closeButton = wx.Button(self, wx.ID_CANCEL, label="&Close")
        for button in (self.setupButton, self.saveButton, self.closeButton):
            buttons.Add(button, 0, wx.LEFT, 8)
        box.Add(buttons, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 16)
        self.SetSizerAndFit(box)
        self.saveButton.SetDefault()
        self.saveButton.Bind(wx.EVT_BUTTON, self._save)
        self.setupButton.Bind(wx.EVT_BUTTON, lambda event: self.on_setup(self))
        self.closeButton.Bind(wx.EVT_BUTTON, lambda event: self.on_close())
        self.Bind(wx.EVT_CLOSE, lambda event: self.on_close())
        self.CentreOnScreen()

    def read_options(self):
        return Options(detail=("concise", "detailed")[self.detail.GetSelection()],
                       max_side=self._sizes[self.size.GetSelection()],
                       threads=self.threads.GetValue(), speak=self.speak.GetValue())

    def focus_initial(self):
        self.detail.SetFocus()

    def _save(self, event):
        self.on_save(self.read_options())
        self.on_close()

    def set_setup_state(self, busy, message):
        self._setting_up = busy
        for control in (self.detail, self.size, self.threads, self.speak, self.saveButton):
            control.Enable(not busy)
        self.setupButton.SetLabel("Cancel &download" if busy else "Download / verify &model")
        self.status.SetLabel(message)
        if not busy:
            self.progress.SetValue(0)
        self.Layout()
