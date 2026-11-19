"""Minimal Kivy app for exercising the p4a WorkManager patch."""

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

print("got here")
from work_manager import Work, cancel, get_info
print("got here1")


class WorkManagerTestApp(App):
    def build(self):
        self.work_name = "heartbeat_once"
        self.message = "hello from WorkManager"

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

        root.add_widget(self._button("Schedule one-time (10s)", self.schedule_once))
        root.add_widget(self._button("Schedule periodic (15m)", self.schedule_periodic))
        root.add_widget(self._button("Schedule failing script (10s)", self.schedule_failing))
        root.add_widget(self._button("Cancel work", self.cancel_work))
        root.add_widget(self._button("Refresh status", lambda _: self.refresh_status()))

        self.status = Label(
            text="Status: (not queried)",
            size_hint_y=None,
            height=80,
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

        Clock.schedule_interval(lambda dt: self.refresh_status(), 1)
        return root

    @staticmethod
    def _button(text, callback):
        button = Button(text=text, size_hint_y=None, height=48)
        button.bind(on_press=callback)
        return button

    @property
    def current_name(self):
        name = self.name_input.text.strip() if self.name_input else self.work_name
        return name or self.work_name

    def _note(self, text):
        self.log.text = "Log:\n{}".format(text)

    def schedule_once(self, _=None, touch=None):
        try:
            Work(
                name=self.current_name,
                script="workers/heartbeat.py",
                args={"message": self.message},
                delay_seconds=10,
                policy="replace",
            ).schedule()
            self._note("Scheduled one-time heartbeat: {}".format(self.current_name))
        except Exception as exc:
            self._note("Schedule failed: {!r}".format(exc))
        self.refresh_status()

    def schedule_periodic(self, _=None, touch=None):
        try:
            Work(
                name="heartbeat_periodic",
                script="workers/heartbeat.py",
                args={"message": "periodic"},
                interval_minutes=15,
                policy="replace",
            ).schedule()
            self._note("Scheduled periodic heartbeat: heartbeat_periodic")
        except Exception as exc:
            self._note("Schedule failed: {!r}".format(exc))
        self.refresh_status()

    def schedule_failing(self, _=None, touch=None):
        try:
            Work(
                name="failing_once",
                script="workers/failing.py",
                args={"message": "expected failure"},
                delay_seconds=10,
                policy="replace",
            ).schedule()
            self._note("Scheduled failing script: failing_once")
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

    def refresh_status(self):
        try:
            one_time = get_info(self.current_name)
        except Exception as exc:
            one_time = "ERROR: {}".format(exc)
        try:
            periodic = get_info("heartbeat_periodic")
        except Exception as exc:
            periodic = "ERROR: {}".format(exc)
        self.status.text = "Status: {}={} periodic={}".format(
            self.current_name, one_time, periodic
        )


if __name__ == "__main__":
    WorkManagerTestApp().run()
