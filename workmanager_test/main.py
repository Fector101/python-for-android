"""Minimal Kivy app for exercising the p4a WorkManager patch."""

import queue
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from work_manager import Work, cancel, cancel_all, get_work_info


class WorkManagerTestApp(App):
    def build(self):
        self.work_name = "heartbeat_once"
        self.message = "hello from WorkManager"
        self.policy = "replace"

        root = BoxLayout(orientation="vertical", padding=12, spacing=8)

        root.add_widget(Label(
            text="p4a WorkManager test",
            size_hint_y=None,
            height=40,
        ))

        name_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44)
        name_row.add_widget(Label(text="Work name:", size_hint_x=0.35))
        self.name_input = TextInput(text=self.work_name, multiline=False)
        name_row.add_widget(self.name_input)
        root.add_widget(name_row)

        constraint_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44)
        constraint_row.add_widget(Label(text="Constraints:", size_hint_x=0.35))
        self.network_cb = CheckBox(activated=False, size_hint_x=None, width=44)
        constraint_row.add_widget(self.network_cb)
        constraint_row.add_widget(Label(text="network", size_hint_x=0.25))
        self.charging_cb = CheckBox(activated=False, size_hint_x=None, width=44)
        constraint_row.add_widget(self.charging_cb)
        constraint_row.add_widget(Label(text="charging", size_hint_x=0.25))
        root.add_widget(constraint_row)

        policy_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44)
        policy_row.add_widget(Label(text="Policy:", size_hint_x=0.35))
        self.policy_button = Button(text=self.policy, size_hint_x=0.65)
        self.policy_button.bind(on_press=self.toggle_policy)
        policy_row.add_widget(self.policy_button)
        root.add_widget(policy_row)

        root.add_widget(self._button("Schedule one-time (10s)", self.schedule_once))
        root.add_widget(self._button("Schedule periodic (15m)", self.schedule_periodic))
        root.add_widget(self._button("Schedule failing script (10s)", self.schedule_failing))
        root.add_widget(self._button("Schedule slow (2s delay, 30s run)", self.schedule_slow))
        root.add_widget(self._button("Cancel work", self.cancel_work))
        root.add_widget(self._button("Cancel all", self.cancel_all_work))
        root.add_widget(self._button("Refresh status", lambda _: self.refresh_status()))

        self.status = Label(
            text="Status: (not queried)",
            size_hint_y=None,
            height=110,
            halign="left",
            valign="top",
        )
        self.status.bind(size=self.status.setter("text_size"))
        root.add_widget(self.status)

        self.log = Label(
            text="Log:",
            size_hint=(1, 1),
            halign="left",
            valign="top",
        )
        self.log.bind(size=self.log.setter("text_size"))
        root.add_widget(self.log)

        # WorkInfo queries use a bounded JNI Future.get(); keep them off the
        # Kivy main thread and only touch widgets when draining the queue.
        self._status_queue = queue.Queue()
        self._poll_now = threading.Event()
        self._stop_polling = threading.Event()
        self._poll_name = self.current_name
        self._poll_thread = threading.Thread(
            target=self._poll_worker,
            name="work-status-poll",
            daemon=True,
        )
        self._poll_thread.start()
        Clock.schedule_interval(lambda dt: self._drain_status(), 0.25)
        return root

    @staticmethod
    def _button(text, callback):
        button = Button(text=text, size_hint_y=None, height=48)
        button.bind(on_press=callback)
        return button

    def toggle_policy(self, _=None, touch=None):
        self.policy = "keep" if self.policy == "replace" else "replace"
        self.policy_button.text = self.policy

    @property
    def current_name(self):
        name = self.name_input.text.strip() if self.name_input else self.work_name
        return name or self.work_name

    @property
    def constraints(self):
        network = getattr(self, "network_cb", None)
        charging = getattr(self, "charging_cb", None)
        return {
            "network_required": bool(network and network.activated),
            "charging_required": bool(charging and charging.activated),
        }

    @staticmethod
    def _constraint_text(constraints):
        parts = []
        if constraints["network_required"]:
            parts.append("network")
        if constraints["charging_required"]:
            parts.append("charging")
        return "requires " + "+".join(parts) if parts else "no constraints"

    def _note(self, text):
        self.log.text = "Log:\n{}".format(text)

    def schedule_once(self, _=None, touch=None):
        constraints = self.constraints
        try:
            Work(
                name=self.current_name,
                script="workers/heartbeat.py",
                args={"message": self.message},
                delay_seconds=10,
                policy=self.policy,
                **constraints,
            ).schedule()
            self._note("Scheduled one-time heartbeat: {} ({}, policy={})".format(
                self.current_name, self._constraint_text(constraints), self.policy))
        except Exception as exc:
            self._note("Schedule failed: {!r}".format(exc))
        self.refresh_status()

    def schedule_periodic(self, _=None, touch=None):
        constraints = self.constraints
        try:
            Work(
                name="heartbeat_periodic",
                script="workers/heartbeat.py",
                args={"message": "periodic"},
                interval_minutes=15,
                policy=self.policy,
                **constraints,
            ).schedule()
            self._note("Scheduled periodic heartbeat: heartbeat_periodic ({}, policy={})".format(
                self._constraint_text(constraints), self.policy))
        except Exception as exc:
            self._note("Schedule failed: {!r}".format(exc))
        self.refresh_status()

    def schedule_failing(self, _=None, touch=None):
        constraints = self.constraints
        try:
            Work(
                name="failing_once",
                script="workers/failing.py",
                args={"message": "expected failure"},
                delay_seconds=10,
                policy=self.policy,
                **constraints,
            ).schedule()
            self._note("Scheduled failing script: failing_once ({}, policy={})".format(
                self._constraint_text(constraints), self.policy))
        except Exception as exc:
            self._note("Schedule failed: {!r}".format(exc))
        self.refresh_status()

    def schedule_slow(self, _=None, touch=None):
        constraints = self.constraints
        try:
            Work(
                name="slow_once",
                script="workers/heartbeat.py",
                args={"message": "slow work", "sleep_seconds": 30},
                delay_seconds=2,
                policy=self.policy,
                **constraints,
            ).schedule()
            self._note("Scheduled slow heartbeat: slow_once ({}, policy={})".format(
                self._constraint_text(constraints), self.policy))
        except Exception as exc:
            self._note("Schedule failed: {!r}".format(exc))
        self.refresh_status()

    def cancel_work(self, _=None, touch=None):
        try:
            cancel(self.current_name)
            self._note("Cancelled: {}".format(self.current_name))
        except Exception as exc:
            self._note("Cancel failed: {!r}".format(exc))
        self.refresh_status()

    def cancel_all_work(self, _=None, touch=None):
        try:
            cancel_all()
            self._note("Cancelled all work")
        except Exception as exc:
            self._note("Cancel all failed: {!r}".format(exc))
        self.refresh_status()

    @staticmethod
    def _format_info(info):
        if info is None:
            return "none"
        parts = [
            "state={}".format(info.state),
            "attempt={}".format(info.run_attempt_count),
            "gen={}".format(info.generation),
            "stop={}".format(info.stop_reason_name),
        ]
        if info.next_schedule_time_ms:
            parts.append("next_ms={}".format(info.next_schedule_time_ms))
        if info.tags:
            parts.append("tags={}".format(",".join(info.tags)))
        if info.output:
            parts.append("output={}".format(info.output))
        if info.progress:
            parts.append("progress={}".format(info.progress))
        return " ".join(parts)

    def refresh_status(self):
        """Ask the polling thread for an update; never blocks the UI thread."""
        self._poll_name = self.current_name
        self._poll_now.set()

    def _poll_worker(self):
        while not self._stop_polling.is_set():
            self._poll_now.wait(1.0)
            self._poll_now.clear()
            if self._stop_polling.is_set():
                break
            name = self._poll_name
            result = {"name": name}
            for key, work_name in (("one_time", name),
                                   ("periodic", "heartbeat_periodic")):
                try:
                    result[key] = get_work_info(work_name)
                except Exception as exc:
                    # A failed query must not kill the polling thread.
                    result[key] = exc
            self._status_queue.put(result)

    def _drain_status(self, dt=None):
        self._poll_name = self.current_name
        latest = None
        while True:
            try:
                latest = self._status_queue.get_nowait()
            except queue.Empty:
                break
        if latest is None:
            return
        for key in ("one_time", "periodic"):
            value = latest.get(key)
            if isinstance(value, Exception):
                self._note("Status query failed: {!r}".format(value))
                latest[key] = None
        self.status.text = "Status: {}: {}\nPeriodic: {}".format(
            latest.get("name", self.current_name),
            self._format_info(latest.get("one_time")),
            self._format_info(latest.get("periodic")),
        )

    def on_stop(self):
        self._stop_polling.set()
        self._poll_now.set()
        if getattr(self, "_poll_thread", None) is not None:
            self._poll_thread.join(timeout=2)


if __name__ == "__main__":
    WorkManagerTestApp().run()
