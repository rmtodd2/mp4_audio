import os
import shlex
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


VIDEO_OUTPUTS = {
    "MP4 (copy video)": {
        "extension": ".mp4",
        "video_args": ["-c:v", "copy"],
        "default_audio_codec": "AAC",
    },
    "MKV (copy video)": {
        "extension": ".mkv",
        "video_args": ["-c:v", "copy"],
        "default_audio_codec": "AAC",
    },
    "Audio only (MP3)": {
        "extension": ".mp3",
        "video_args": ["-vn"],
        "default_audio_codec": "MP3",
    },
    "Audio only (M4A)": {
        "extension": ".m4a",
        "video_args": ["-vn"],
        "default_audio_codec": "AAC",
    },
    "Audio only (WAV)": {
        "extension": ".wav",
        "video_args": ["-vn"],
        "default_audio_codec": "WAV",
    },
}


AUDIO_CODECS = {
    "AAC": {"args": ["-c:a", "aac"], "supports_bitrate": True},
    "MP3": {"args": ["-c:a", "libmp3lame"], "supports_bitrate": True},
    "WAV": {"args": ["-c:a", "pcm_s16le"], "supports_bitrate": False},
}


BITRATE_CHOICES = ["96k", "128k", "160k", "192k", "256k", "320k"]
NORMALIZE_PRESETS = {
    "Off": None,
    "Podcast / Voice (-16 LUFS)": "loudnorm=I=-16:LRA=7:TP=-1.5",
    "Streaming / Video (-14 LUFS)": "loudnorm=I=-14:LRA=11:TP=-1.5",
    "Music (-12 LUFS)": "loudnorm=I=-12:LRA=8:TP=-1.0",
}


def which_ffmpeg() -> str | None:
    from shutil import which
    return which("ffmpeg")


def run_ffmpeg(cmd_list, log_cb):
    proc = subprocess.Popen(
        cmd_list,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        universal_newlines=True,
        bufsize=1,
    )

    def pump(stream):
        for line in iter(stream.readline, ""):
            log_cb(line.rstrip())
        stream.close()

    t_err = threading.Thread(target=pump, args=(proc.stderr,), daemon=True)
    t_out = threading.Thread(target=pump, args=(proc.stdout,), daemon=True)
    t_err.start()
    t_out.start()

    return proc.wait()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MP4 Audio Tool (FFmpeg)")
        self.geometry("860x700")
        self.minsize(860, 700)

        self.in_path = tk.StringVar(value="")
        self.out_path = tk.StringVar(value="")
        self.output_mode = tk.StringVar(value="MP4 (copy video)")
        self.audio_codec = tk.StringVar(value="AAC")
        self.audio_bitrate = tk.StringVar(value="192k")
        self.gain_db = tk.DoubleVar(value=0.0)
        self.normalize_preset = tk.StringVar(value="Off")
        self.mute = tk.BooleanVar(value=False)
        self.trim_start = tk.StringVar(value="")
        self.trim_duration = tk.StringVar(value="")
        self.overwrite_existing = tk.BooleanVar(value=True)
        self.open_folder_after = tk.BooleanVar(value=False)
        self.busy = False

        self._build_ui()
        self._update_gain_label()
        self._sync_output_settings()

        if not which_ffmpeg():
            messagebox.showwarning(
                "FFmpeg not found",
                "FFmpeg was not found in your PATH.\n\n"
                "Install FFmpeg and ensure 'ffmpeg' runs from Command Prompt or Terminal.\n"
                "Then restart this app."
            )

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        frm_in = tk.LabelFrame(self, text="Input")
        frm_in.pack(fill="x", **pad)

        ent_in = tk.Entry(frm_in, textvariable=self.in_path)
        ent_in.pack(side="left", fill="x", expand=True, padx=8, pady=8)

        tk.Button(frm_in, text="Browse...", command=self.browse_in).pack(side="left", padx=8, pady=8)

        frm_out = tk.LabelFrame(self, text="Output")
        frm_out.pack(fill="x", **pad)

        top_out = tk.Frame(frm_out)
        top_out.pack(fill="x", padx=8, pady=(8, 0))
        tk.Label(top_out, text="Type:").pack(side="left")
        self.cmb_output = ttk.Combobox(
            top_out,
            textvariable=self.output_mode,
            values=list(VIDEO_OUTPUTS.keys()),
            state="readonly",
            width=22,
        )
        self.cmb_output.pack(side="left", padx=(8, 16))
        self.cmb_output.bind("<<ComboboxSelected>>", lambda *_: self._sync_output_settings())

        ent_out = tk.Entry(frm_out, textvariable=self.out_path)
        ent_out.pack(side="left", fill="x", expand=True, padx=8, pady=8)

        tk.Button(frm_out, text="Save As...", command=self.choose_out).pack(side="left", padx=8, pady=8)

        frm_audio = tk.LabelFrame(self, text="Audio Controls")
        frm_audio.pack(fill="x", **pad)

        gain_row = tk.Frame(frm_audio)
        gain_row.pack(fill="x", padx=8, pady=8)
        tk.Label(gain_row, text="Gain (dB):").pack(side="left")
        tk.Scale(
            gain_row,
            from_=-30,
            to=30,
            orient="horizontal",
            resolution=0.5,
            variable=self.gain_db,
            length=420,
            command=lambda *_: self._update_gain_label(),
        ).pack(side="left", padx=10)

        self.lbl_gain = tk.Label(gain_row, text="", width=10)
        self.lbl_gain.pack(side="left")

        row2 = tk.Frame(frm_audio)
        row2.pack(fill="x", padx=8, pady=(0, 8))

        tk.Checkbutton(row2, text="Mute audio", variable=self.mute, command=self._update_audio_controls).pack(side="left")

        tk.Label(row2, text="Normalize:").pack(side="left", padx=(18, 8))
        self.cmb_normalize = ttk.Combobox(
            row2,
            textvariable=self.normalize_preset,
            values=list(NORMALIZE_PRESETS.keys()),
            state="readonly",
            width=28,
        )
        self.cmb_normalize.pack(side="left")

        codec_row = tk.Frame(frm_audio)
        codec_row.pack(fill="x", padx=8, pady=(0, 8))
        tk.Label(codec_row, text="Audio codec:").pack(side="left")
        self.cmb_codec = ttk.Combobox(
            codec_row,
            textvariable=self.audio_codec,
            values=list(AUDIO_CODECS.keys()),
            state="readonly",
            width=10,
        )
        self.cmb_codec.pack(side="left", padx=(8, 18))
        self.cmb_codec.bind("<<ComboboxSelected>>", lambda *_: self._update_audio_controls())

        tk.Label(codec_row, text="Bitrate:").pack(side="left")
        self.cmb_bitrate = ttk.Combobox(
            codec_row,
            textvariable=self.audio_bitrate,
            values=BITRATE_CHOICES,
            state="readonly",
            width=8,
        )
        self.cmb_bitrate.pack(side="left", padx=(8, 0))

        frm_trim = tk.LabelFrame(self, text="Trim (Optional)")
        frm_trim.pack(fill="x", **pad)

        tk.Label(frm_trim, text="Start time (hh:mm:ss or seconds):").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        tk.Entry(frm_trim, textvariable=self.trim_start, width=18).grid(row=0, column=1, sticky="w", padx=8, pady=8)

        tk.Label(frm_trim, text="Duration (hh:mm:ss or seconds):").grid(row=0, column=2, sticky="w", padx=8, pady=8)
        tk.Entry(frm_trim, textvariable=self.trim_duration, width=18).grid(row=0, column=3, sticky="w", padx=8, pady=8)

        frm_opts = tk.LabelFrame(self, text="Options")
        frm_opts.pack(fill="x", **pad)

        tk.Checkbutton(
            frm_opts,
            text="Overwrite output file if it already exists",
            variable=self.overwrite_existing,
        ).pack(anchor="w", padx=8, pady=(8, 4))
        tk.Checkbutton(
            frm_opts,
            text="Open output folder after export",
            variable=self.open_folder_after,
        ).pack(anchor="w", padx=8, pady=(0, 8))

        help_txt = (
            "Notes:\n"
            "- Video outputs copy the video stream for fast exports without video quality loss.\n"
            "- Audio filters are applied in this order: gain or mute, then normalization.\n"
            "- Normalization uses FFmpeg loudnorm in a simple single-pass mode.\n"
            "- Trim values are optional; leave them blank to export the full file.\n"
        )
        tk.Label(self, text=help_txt, justify="left").pack(anchor="w", padx=18, pady=(0, 8))

        frm_act = tk.Frame(self)
        frm_act.pack(fill="x", **pad)

        self.btn_export = tk.Button(frm_act, text="Export", command=self.export)
        self.btn_export.pack(side="left")

        tk.Button(frm_act, text="Clear Log", command=self.clear_log).pack(side="left", padx=10)

        frm_log = tk.LabelFrame(self, text="FFmpeg Log")
        frm_log.pack(fill="both", expand=True, **pad)

        self.txt = tk.Text(frm_log, height=16, wrap="none")
        self.txt.pack(fill="both", expand=True, padx=8, pady=8)

        self.status = tk.StringVar(value="Ready.")
        tk.Label(self, textvariable=self.status, anchor="w").pack(fill="x", padx=10, pady=(0, 10))

    def _update_gain_label(self):
        self.lbl_gain.config(text=f"{self.gain_db.get():.1f} dB")

    def _sync_output_settings(self):
        mode = VIDEO_OUTPUTS[self.output_mode.get()]
        self.audio_codec.set(mode["default_audio_codec"])
        self._update_audio_controls()

        in_path = self.in_path.get().strip()
        out_path = self.out_path.get().strip()
        if in_path and (not out_path or self._looks_auto_named(out_path)):
            self.out_path.set(self._suggest_output_path(in_path))

    def _update_audio_controls(self):
        codec_info = AUDIO_CODECS[self.audio_codec.get()]
        bitrate_state = "readonly" if codec_info["supports_bitrate"] else "disabled"
        self.cmb_bitrate.config(state=bitrate_state)

        if not codec_info["supports_bitrate"]:
            self.audio_bitrate.set("")
        elif self.audio_bitrate.get() not in BITRATE_CHOICES:
            self.audio_bitrate.set("192k")

    def _looks_auto_named(self, path: str) -> bool:
        root, _ = os.path.splitext(path)
        return root.endswith("_audio")

    def _suggest_output_path(self, in_path: str) -> str:
        base, _ = os.path.splitext(in_path)
        extension = VIDEO_OUTPUTS[self.output_mode.get()]["extension"]
        return f"{base}_audio{extension}"

    def log(self, line: str):
        def _append():
            self.txt.insert("end", line + "\n")
            self.txt.see("end")

        self.after(0, _append)

    def clear_log(self):
        self.txt.delete("1.0", "end")

    def browse_in(self):
        path = filedialog.askopenfilename(
            title="Select media file",
            filetypes=[
                ("Media files", "*.mp4;*.mkv;*.mov;*.m4v;*.mp3;*.wav;*.m4a"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        self.in_path.set(path)
        self.out_path.set(self._suggest_output_path(path))

    def choose_out(self):
        mode = VIDEO_OUTPUTS[self.output_mode.get()]
        path = filedialog.asksaveasfilename(
            title="Save output as...",
            defaultextension=mode["extension"],
            filetypes=[(f"{mode['extension']} files", f"*{mode['extension']}"), ("All files", "*.*")],
        )
        if path:
            self.out_path.set(path)

    def _set_busy(self, busy: bool):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.btn_export.config(state=state)

    def _validate_time_value(self, value: str, label: str) -> str | None:
        value = value.strip()
        if not value:
            return None

        allowed = set("0123456789:.")
        if any(ch not in allowed for ch in value):
            raise ValueError(f"{label} contains unsupported characters.")

        if value.count(":") > 2:
            raise ValueError(f"{label} must be seconds or hh:mm:ss.")

        return value

    def _build_audio_filter(self):
        filters = []

        if self.mute.get():
            filters.append("volume=0")
        else:
            gain = float(self.gain_db.get())
            if abs(gain) > 1e-9:
                filters.append(f"volume={gain}dB")

        normalize_filter = NORMALIZE_PRESETS[self.normalize_preset.get()]
        if normalize_filter:
            filters.append(normalize_filter)

        return ",".join(filters) if filters else None

    def _build_command(self, ffmpeg: str, in_path: str, out_path: str) -> list[str]:
        mode = VIDEO_OUTPUTS[self.output_mode.get()]
        codec_info = AUDIO_CODECS[self.audio_codec.get()]
        cmd = [ffmpeg, "-hide_banner"]

        cmd.append("-y" if self.overwrite_existing.get() else "-n")

        trim_start = self._validate_time_value(self.trim_start.get(), "Start time")
        trim_duration = self._validate_time_value(self.trim_duration.get(), "Duration")
        if trim_start:
            cmd += ["-ss", trim_start]

        cmd += ["-i", in_path]

        if trim_duration:
            cmd += ["-t", trim_duration]

        if mode["video_args"] == ["-vn"]:
            cmd += ["-map", "0:a:0?"]
        else:
            cmd += ["-map", "0:v?", "-map", "0:a?"]

        audio_filter = self._build_audio_filter()
        if audio_filter:
            cmd += ["-af", audio_filter]

        cmd += mode["video_args"]
        cmd += codec_info["args"]

        if codec_info["supports_bitrate"]:
            cmd += ["-b:a", self.audio_bitrate.get()]

        if mode["extension"] in {".mp4", ".m4a"}:
            cmd += ["-movflags", "+faststart"]

        cmd.append(out_path)
        return cmd

    def _open_output_folder(self, out_path: str):
        folder = os.path.dirname(out_path) or "."
        try:
            os.startfile(folder)
        except OSError as exc:
            self.log(f"Could not open folder: {exc}")

    def export(self):
        if self.busy:
            return

        ffmpeg = which_ffmpeg()
        if not ffmpeg:
            messagebox.showerror("FFmpeg not found", "FFmpeg is required. Install it and ensure it's in PATH.")
            return

        in_path = self.in_path.get().strip()
        out_path = self.out_path.get().strip()

        if not in_path or not os.path.exists(in_path):
            messagebox.showerror("Missing input", "Please select a valid input file.")
            return
        if not out_path:
            messagebox.showerror("Missing output", "Please choose an output file path.")
            return
        if os.path.abspath(in_path) == os.path.abspath(out_path):
            messagebox.showerror("Invalid output", "Output file must be different from input file.")
            return

        out_dir = os.path.dirname(out_path)
        if out_dir and not os.path.isdir(out_dir):
            messagebox.showerror("Invalid output", "The output folder does not exist.")
            return

        try:
            cmd = self._build_command(ffmpeg, in_path, out_path)
        except ValueError as exc:
            messagebox.showerror("Invalid option", str(exc))
            return

        self.clear_log()
        self.log("Running command:")
        self.log(" ".join(shlex.quote(x) for x in cmd))
        self.status.set("Exporting...")
        self._set_busy(True)

        def worker():
            rc = run_ffmpeg(cmd, self.log)

            def done():
                self._set_busy(False)
                if rc == 0 and os.path.exists(out_path):
                    self.status.set("Done.")
                    if self.open_folder_after.get():
                        self._open_output_folder(out_path)
                    messagebox.showinfo("Export complete", f"Saved:\n{out_path}")
                else:
                    self.status.set("Failed.")
                    messagebox.showerror("Export failed", "FFmpeg returned an error. Check the log for details.")

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
