# FULL BACKUP: local p4a WorkManager patch (port of PR #2613)

Created 2026-11-19. This file is self-contained: it records every changed/new
file so the patch can be reconstructed if the session or working tree is lost.

## Status / location

- p4a checkout: `/home/fabian/Documents/widget/python-for-android`
- git branch: `fix-broadcast-receiver-export-flag`
- State: **UNCOMMITTED** (tracked modifications + untracked new files). Never
  run `git clean` / `git checkout .` there or the patch is lost.
- Based on closed upstream PR https://github.com/kivy/python-for-android/pull/2613
  but manually ported to the 2026 checkout (SDL3, Gradle 8.14.3/AGP 8.11,
  `.pyc` packaging, `service_data` manifests). Not a clean PR-only state.
- Test app: `/home/fabian/Documents/python-android/workmanager_test/`
- Final APK: `workmanager_test/bin/workmanagertest-0.1-arm64-v8a-debug.apk`
- Verified on device `H6YPAAWSYLP7CAIN`: both workers pass and a worker-posted
  notification appears in `dumpsys notification`.

## File inventory

Tracked modifications (9):

- `pythonforandroid/bootstraps/_sdl_common/build/templates/AndroidManifest.tmpl.xml`
- `pythonforandroid/bootstraps/common/build/build.py`
- `pythonforandroid/bootstraps/common/build/jni/application/src/start.c`
- `pythonforandroid/bootstraps/common/build/src/main/java/org/kivy/android/PythonService.java`
- `pythonforandroid/bootstraps/common/build/templates/build.tmpl.gradle`
- `pythonforandroid/bootstraps/qt/build/templates/AndroidManifest.tmpl.xml`
- `pythonforandroid/bootstraps/service_library/build/templates/AndroidManifest.tmpl.xml`
- `pythonforandroid/bootstraps/service_only/build/templates/AndroidManifest.tmpl.xml`
- `pythonforandroid/bootstraps/webview/build/templates/AndroidManifest.tmpl.xml`

Untracked new files (3):

- `pythonforandroid/bootstraps/common/build/src/main/java/org/kivy/android/PythonWorker.java`
- `pythonforandroid/bootstraps/common/build/templates/Worker.tmpl.java`
- `pythonforandroid/bootstraps/common/build/templates/WorkerService.tmpl.java`

## 1. FULL DIFF OF TRACKED P4A CHANGES

```diff
diff --git a/pythonforandroid/bootstraps/_sdl_common/build/templates/AndroidManifest.tmpl.xml b/pythonforandroid/bootstraps/_sdl_common/build/templates/AndroidManifest.tmpl.xml
index 66ec71d0..a2b91289 100644
--- a/pythonforandroid/bootstraps/_sdl_common/build/templates/AndroidManifest.tmpl.xml
+++ b/pythonforandroid/bootstraps/_sdl_common/build/templates/AndroidManifest.tmpl.xml
@@ -125,6 +125,12 @@
         {% for name in native_services %}
         <service android:name="{{ name }}" />
         {% endfor %}
+        {% for name in worker_names %}
+        <service android:name="{{ args.package }}.{{ name|capitalize }}WorkerService"
+                 android:process=":worker_{{ name }}"
+                 android:exported="false"
+                 android:stopWithTask="true" />
+        {% endfor %}
 
         {% if args.billing_pubkey %}
         <service android:name="org.kivy.android.billing.BillingReceiver"
diff --git a/pythonforandroid/bootstraps/common/build/build.py b/pythonforandroid/bootstraps/common/build/build.py
index 04f56ac3..22b490a6 100644
--- a/pythonforandroid/bootstraps/common/build/build.py
+++ b/pythonforandroid/bootstraps/common/build/build.py
@@ -570,6 +570,49 @@ main.py that loads it.''')
             base_service_class=base_service_class,
         )
 
+    worker_names = []
+    for spec in args.workers:
+        parts = spec.split(':')
+        if len(parts) != 2 or not parts[0] or not parts[1]:
+            raise ValueError(
+                'Invalid --worker value {!r}. Expected NAME:PATH_TO_PY'.format(spec)
+            )
+        name, entrypoint = parts
+        if not name.replace('_', '').isalnum() or name[0].isdigit():
+            raise ValueError(
+                'Worker name {!r} must be a Java identifier (letters, digits '
+                'and underscores, not starting with a digit)'.format(name)
+            )
+        if name in worker_names:
+            raise ValueError('Duplicate worker name {!r}'.format(name))
+
+        worker_names.append(name)
+        worker_target_path = (
+            'src/main/java/{}/{}Worker.java'.format(
+                args.package.replace('.', '/'), name.capitalize()
+            )
+        )
+        render(
+            'Worker.tmpl.java',
+            worker_target_path,
+            name=name,
+            entrypoint=entrypoint,
+            args=args,
+        )
+
+        worker_service_target_path = (
+            'src/main/java/{}/{}WorkerService.java'.format(
+                args.package.replace('.', '/'), name.capitalize()
+            )
+        )
+        render(
+            'WorkerService.tmpl.java',
+            worker_service_target_path,
+            name=name,
+            entrypoint=entrypoint,
+            args=args,
+        )
+
     # Find the SDK directory and target API
     with open('project.properties', 'r') as fileh:
         target = fileh.read().strip()
@@ -588,6 +631,10 @@ main.py that loads it.''')
         sdk_dir = fileh.read().strip()
     sdk_dir = sdk_dir[8:]
 
+    # WorkManager 2.7+ requires API 31. Older versions are kept for older
+    # projects, but test builds should target a current API.
+    work_manager_version = '2.9.0' if android_api >= 31 else '2.6.0'
+
     # Try to build with the newest available build tools
     ignored = {".DS_Store", ".ds_store"}
     build_tools_versions = [x for x in listdir(join(sdk_dir, 'build-tools')) if x not in ignored]
@@ -617,6 +664,7 @@ main.py that loads it.''')
         "args": args,
         "service": service,
         "service_data": service_data,
+        "worker_names": worker_names,
         "android_api": android_api,
         "debug": "debug" in args.build_mode,
         "native_services": args.native_services,
@@ -646,6 +694,7 @@ main.py that loads it.''')
         build_tools_version=build_tools_version,
         debug_build="debug" in args.build_mode,
         is_library=(get_bootstrap_name() == 'service_library'),
+        work_manager_version=work_manager_version,
         )
 
     # gradle properties
@@ -903,6 +952,9 @@ tools directory of the Android SDK.
     ap.add_argument('--service', dest='services', action='append', default=[],
                     help='Declare a new service entrypoint: '
                          'NAME:PATH_TO_PY[:foreground]')
+    ap.add_argument('--worker', dest='workers', action='append', default=[],
+                    help='Declare a new WorkManager worker entrypoint: '
+                         'NAME:PATH_TO_PY')
     ap.add_argument('--native-service', dest='native_services', action='append', default=[],
                     help='Declare a new native service: '
                          'package.name.service')
@@ -1168,6 +1220,11 @@ def parse_args_and_make_package(args=None):
               '--launcher (SDL2/SDL3 bootstrap only)' +
               'to have something to launch inside the .apk!')
         sys.exit(1)
+
+    if args.workers and not args.enable_androidx:
+        print('WARNING: Enabling androidx for worker support')
+        args.enable_androidx = True
+
     make_package(args)
 
     return args
diff --git a/pythonforandroid/bootstraps/common/build/jni/application/src/start.c b/pythonforandroid/bootstraps/common/build/jni/application/src/start.c
index dc33b5d3..b5debef6 100644
--- a/pythonforandroid/bootstraps/common/build/jni/application/src/start.c
+++ b/pythonforandroid/bootstraps/common/build/jni/application/src/start.c
@@ -7,6 +7,7 @@
 
 #include <stdio.h>
 #include <stdlib.h>
+#include <stdbool.h>
 #include <unistd.h>
 #include <dirent.h>
 #include <dlfcn.h>
@@ -195,8 +196,71 @@ char *setup_symlinks() {
 }
 
 
-/* int main(int argc, char **argv) { */
-int main(int argc, char *argv[]) {
+/*
+ * Worker scripts are executed through runpy so that SystemExit(code) becomes a
+ * return value instead of terminating the remote worker process before Java
+ * can complete the WorkManager future. runpy also handles the .pyc files that
+ * newer p4a builds prefer over .py sources.
+ */
+#if PY_MAJOR_VERSION >= 3
+static int run_worker_script(const char *worker_entrypoint) {
+  const char *command =
+      "import os, runpy, sys\n"
+      "os.environ['ANDROID_ENTRYPOINT'] = sys.p4a_worker_entrypoint\n"
+      "sys.argv = [sys.p4a_worker_entrypoint]\n"
+      "sys.p4a_worker_exit_code = 0\n"
+      "try:\n"
+      "    runpy.run_path(sys.p4a_worker_entrypoint, run_name='__main__')\n"
+      "except SystemExit as _p4a_exit:\n"
+      "    _p4a_code = _p4a_exit.code\n"
+      "    if _p4a_code is None:\n"
+      "        sys.p4a_worker_exit_code = 0\n"
+      "    elif isinstance(_p4a_code, int):\n"
+      "        sys.p4a_worker_exit_code = _p4a_code\n"
+      "    else:\n"
+      "        sys.p4a_worker_exit_code = 1\n"
+      "        print(_p4a_code, file=sys.stderr)\n";
+
+  /* os.environ is a snapshot from interpreter startup, so a C setenv() after
+   * Py_Initialize() is invisible to Python. Hand the resolved path over via
+   * sys and mirror it into os.environ before running the script. */
+  PyObject *py_entrypoint = PyUnicode_FromString(worker_entrypoint);
+  if (py_entrypoint == NULL) {
+    PyErr_Clear();
+    return 1;
+  }
+  PySys_SetObject("p4a_worker_entrypoint", py_entrypoint);
+  Py_DECREF(py_entrypoint);
+
+  if (PyRun_SimpleString(command) != 0) {
+    return 1;
+  }
+
+  int result = 0;
+  PyObject *code = PySys_GetObject("p4a_worker_exit_code");
+  if (code != NULL && code != Py_None) {
+    if (PyLong_Check(code)) {
+      long value = PyLong_AsLong(code);
+      if (PyErr_Occurred()) {
+        PyErr_Clear();
+        result = 1;
+      } else {
+        result = (int)value;
+      }
+    } else {
+      result = 1;
+    }
+  }
+  return result;
+}
+#endif
+
+/*
+ * run_python() is the shared body for the app entry point, p4a services and
+ * WorkManager workers. call_exit=false is used by workers, where returning the
+ * status to Java is preferable to terminating the whole process here.
+ */
+static int run_python(int argc, char *argv[], bool call_exit) {
 
   char *env_argument = NULL;
   char *env_entrypoint = NULL;
@@ -455,6 +519,11 @@ int main(int argc, char *argv[]) {
   }
   // LOGP("Entrypoint is:");
   // LOGP(entrypoint);
+
+  /* runpy must receive the resolved path: p4a packages worker scripts as .pyc,
+   * so the requested .py name does not exist on the device. */
+  setenv("ANDROID_ENTRYPOINT", entrypoint, 1);
+
   fd = fopen(entrypoint, "r");
   if (fd == NULL) {
     LOGP("Open the entrypoint failed");
@@ -463,33 +532,57 @@ int main(int argc, char *argv[]) {
   }
   /* run python !
    */
-  ret = PyRun_SimpleFile(fd, entrypoint);
-  fclose(fd);
-
-  if (PyErr_Occurred() != NULL) {
-    ret = 1;
-    PyErr_Print(); /* This exits with the right code if SystemExit. */
-    PyObject *f = PySys_GetObject("stdout");
-    if (PyFile_WriteString("\n", f))
-      PyErr_Clear();
+#if PY_MAJOR_VERSION >= 3
+  if (!call_exit) {
+    /* runpy opens the script itself; it understands .py and .pyc. */
+    fclose(fd);
+    ret = run_worker_script(entrypoint);
+  } else {
+#endif
+    ret = PyRun_SimpleFile(fd, entrypoint);
+    fclose(fd);
+
+    if (PyErr_Occurred() != NULL) {
+      ret = 1;
+      PyErr_Print();
+      PyObject *f = PySys_GetObject("stdout");
+      if (f != NULL && PyFile_WriteString("\n", f))
+        PyErr_Clear();
+    }
+#if PY_MAJOR_VERSION >= 3
   }
+#endif
 
   LOGP("Python for android ended.");
 
+  /* Regular p4a entry points must terminate the process: incomplete CPython
+   * shutdown has caused problems on restart. Workers instead need to hand the
+   * exit status back to Java so WorkManager can mark the work succeeded/failed;
+   * their disposable process is stopped by WorkerService.onDestroy(). */
+  if (call_exit) {
+    char terminatecmd[256];
+    snprintf(terminatecmd, sizeof(terminatecmd),
+             "import sys; sys.exit(%d)\n", ret);
+    PyRun_SimpleString(terminatecmd);
+    LOGP("Unexpectedly reached python finalization");
+  }
+
 #if PY_MAJOR_VERSION < 3
   Py_Finalize();
-  LOGP("Unexpectedly reached Py_FinalizeEx(), but was successful.");
 #else
   if (Py_FinalizeEx() != 0) {  // properly check success on Python 3
-    LOGP("Unexpectedly reached Py_FinalizeEx(), and got error!");
+    LOGP("Py_FinalizeEx() returned an error!");
   }
 #endif
 
-  exit(ret);
   return ret;
 }
 
-JNIEXPORT void JNICALL Java_org_kivy_android_PythonService_nativeStart(
+int main(int argc, char *argv[]) {
+  return run_python(argc, argv, true);
+}
+
+static jint native_start(
     JNIEnv *env,
     jobject thiz,
     jstring j_android_private,
@@ -498,7 +591,8 @@ JNIEXPORT void JNICALL Java_org_kivy_android_PythonService_nativeStart(
     jstring j_python_name,
     jstring j_python_home,
     jstring j_python_path,
-    jstring j_arg) {
+    jstring j_arg,
+    bool call_exit) {
   jboolean iscopy;
   const char *android_private =
       (*env)->GetStringUTFChars(env, j_android_private, &iscopy);
@@ -526,10 +620,42 @@ JNIEXPORT void JNICALL Java_org_kivy_android_PythonService_nativeStart(
   setenv("P4A_BOOTSTRAP", bootstrap_name, 1);
 
   char *argv[] = {"."};
-  /* ANDROID_ARGUMENT points to service subdir,
-   * so main() will run main.py from this dir
+  /* ANDROID_ARGUMENT points to the app root, so run_python() resolves the
+   * entrypoint relative to the unpacked files/app directory.
    */
-  main(1, argv);
+  return run_python(1, argv, call_exit);
+}
+
+JNIEXPORT jint JNICALL Java_org_kivy_android_PythonService_nativeStart(
+    JNIEnv *env,
+    jobject thiz,
+    jstring j_android_private,
+    jstring j_android_argument,
+    jstring j_service_entrypoint,
+    jstring j_python_name,
+    jstring j_python_home,
+    jstring j_python_path,
+    jstring j_arg) {
+  LOGP("Entering org.kivy.android.PythonService.nativeStart");
+  return native_start(env, thiz, j_android_private, j_android_argument,
+                      j_service_entrypoint, j_python_name, j_python_home,
+                      j_python_path, j_arg, true);
+}
+
+JNIEXPORT jint JNICALL Java_org_kivy_android_PythonWorker_nativeStart(
+    JNIEnv *env,
+    jobject thiz,
+    jstring j_android_private,
+    jstring j_android_argument,
+    jstring j_service_entrypoint,
+    jstring j_python_name,
+    jstring j_python_home,
+    jstring j_python_path,
+    jstring j_arg) {
+  LOGP("Entering org.kivy.android.PythonWorker.nativeStart");
+  return native_start(env, thiz, j_android_private, j_android_argument,
+                      j_service_entrypoint, j_python_name, j_python_home,
+                      j_python_path, j_arg, false);
 }
 
 #if defined(BOOTSTRAP_NAME_WEBVIEW) || defined(BOOTSTRAP_NAME_SERVICEONLY)
diff --git a/pythonforandroid/bootstraps/common/build/src/main/java/org/kivy/android/PythonService.java b/pythonforandroid/bootstraps/common/build/src/main/java/org/kivy/android/PythonService.java
index 8433aa46..1db10780 100644
--- a/pythonforandroid/bootstraps/common/build/src/main/java/org/kivy/android/PythonService.java
+++ b/pythonforandroid/bootstraps/common/build/src/main/java/org/kivy/android/PythonService.java
@@ -217,7 +217,7 @@ public class PythonService extends Service implements Runnable {
     }
 
     // Native part
-    public static native void nativeStart(
+    public static native int nativeStart(
             String androidPrivate,
             String androidArgument,
             String serviceEntrypoint,
diff --git a/pythonforandroid/bootstraps/common/build/templates/build.tmpl.gradle b/pythonforandroid/bootstraps/common/build/templates/build.tmpl.gradle
index 5ea5e0cf..7916cbab 100644
--- a/pythonforandroid/bootstraps/common/build/templates/build.tmpl.gradle
+++ b/pythonforandroid/bootstraps/common/build/templates/build.tmpl.gradle
@@ -128,5 +128,11 @@ dependencies {
     {% if args.presplash_lottie %}
     implementation 'com.airbnb.android:lottie:6.1.0'
     {%- endif %}
+    {%- if args.workers %}
+    implementation 'androidx.annotation:annotation:1.3.0'
+    implementation 'androidx.concurrent:concurrent-futures:1.1.0'
+    implementation 'androidx.work:work-runtime:{{ work_manager_version }}'
+    implementation 'androidx.work:work-multiprocess:{{ work_manager_version }}'
+    {%- endif %}
 }
 
diff --git a/pythonforandroid/bootstraps/qt/build/templates/AndroidManifest.tmpl.xml b/pythonforandroid/bootstraps/qt/build/templates/AndroidManifest.tmpl.xml
index 62c9390e..9fb46534 100644
--- a/pythonforandroid/bootstraps/qt/build/templates/AndroidManifest.tmpl.xml
+++ b/pythonforandroid/bootstraps/qt/build/templates/AndroidManifest.tmpl.xml
@@ -102,6 +102,12 @@
         {% for name in native_services %}
         <service android:name="{{ name }}" />
         {% endfor %}
+        {% for name in worker_names %}
+        <service android:name="{{ args.package }}.{{ name|capitalize }}WorkerService"
+                 android:process=":worker_{{ name }}"
+                 android:exported="false"
+                 android:stopWithTask="true" />
+        {% endfor %}
 
     {% for a in args.add_activity  %}
     <activity android:name="{{ a }}"></activity>
diff --git a/pythonforandroid/bootstraps/service_library/build/templates/AndroidManifest.tmpl.xml b/pythonforandroid/bootstraps/service_library/build/templates/AndroidManifest.tmpl.xml
index 51f0d8a0..d514702d 100644
--- a/pythonforandroid/bootstraps/service_library/build/templates/AndroidManifest.tmpl.xml
+++ b/pythonforandroid/bootstraps/service_library/build/templates/AndroidManifest.tmpl.xml
@@ -15,6 +15,12 @@
                  android:process=":service_{{ name }}"
                  android:exported="true" />
         {% endfor %}
+        {% for name in worker_names %}
+        <service android:name="{{ args.package }}.{{ name|capitalize }}WorkerService"
+                 android:process=":worker_{{ name }}"
+                 android:exported="false"
+                 android:stopWithTask="true" />
+        {% endfor %}
     {{ args.extra_manifest_application_xml }}
     </application>
 
diff --git a/pythonforandroid/bootstraps/service_only/build/templates/AndroidManifest.tmpl.xml b/pythonforandroid/bootstraps/service_only/build/templates/AndroidManifest.tmpl.xml
index fda2bcd3..a953f6e0 100644
--- a/pythonforandroid/bootstraps/service_only/build/templates/AndroidManifest.tmpl.xml
+++ b/pythonforandroid/bootstraps/service_only/build/templates/AndroidManifest.tmpl.xml
@@ -80,6 +80,12 @@
                  android:process=":service_{{ name }}"
                  android:exported="true" />
         {% endfor %}
+        {% for name in worker_names %}
+        <service android:name="{{ args.package }}.{{ name|capitalize }}WorkerService"
+                 android:process=":worker_{{ name }}"
+                 android:exported="false"
+                 android:stopWithTask="true" />
+        {% endfor %}
 
         {% if args.billing_pubkey %}
         <service android:name="org.kivy.android.billing.BillingReceiver"
diff --git a/pythonforandroid/bootstraps/webview/build/templates/AndroidManifest.tmpl.xml b/pythonforandroid/bootstraps/webview/build/templates/AndroidManifest.tmpl.xml
index b87c5d51..53e72e7b 100644
--- a/pythonforandroid/bootstraps/webview/build/templates/AndroidManifest.tmpl.xml
+++ b/pythonforandroid/bootstraps/webview/build/templates/AndroidManifest.tmpl.xml
@@ -88,6 +88,12 @@
                  {% endif %}
                  android:process=":service_{{ name }}" />
         {% endfor %}
+        {% for name in worker_names %}
+        <service android:name="{{ args.package }}.{{ name|capitalize }}WorkerService"
+                 android:process=":worker_{{ name }}"
+                 android:exported="false"
+                 android:stopWithTask="true" />
+        {% endfor %}
 
         {% if args.billing_pubkey %}
         <service android:name="org.kivy.android.billing.BillingReceiver"
```

## 2. NEW FILE: pythonforandroid/bootstraps/common/build/src/main/java/org/kivy/android/PythonWorker.java

```java
package org.kivy.android;

import android.content.Context;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.concurrent.futures.CallbackToFutureAdapter;
import androidx.work.ListenableWorker.Result;
import androidx.work.WorkerParameters;
import androidx.work.multiprocess.RemoteListenableWorker;

import com.google.common.util.concurrent.ListenableFuture;

import java.io.File;
import java.util.concurrent.Executors;

/**
 * Base class for p4a WorkManager workers.
 *
 * A p4a process can only initialise CPython once, so workers run in the
 * dedicated :worker_* process created by the generated WorkerService. The
 * native entry point runs the Python script without calling sys.exit() and
 * returns its status so WorkManager gets a real success/failure result.
 */
public abstract class PythonWorker extends RemoteListenableWorker {
    private static final String TAG = "PythonWorker";

    /** A p4a process may only initialise CPython once at a time. */
    private static final Object PYTHON_LOCK = new Object();

    /**
     * Application context of the remote worker process. Python libraries such
     * as android_notify need a real Android Context, but PythonActivity.mActivity
     * and PythonService.mService are both null in the :worker_* process.
     */
    public static Context mWorkerContext = null;

    public static Context getWorkerContext() {
        return mWorkerContext;
    }

    /** WorkRequest Data key for the string passed as PYTHON_SERVICE_ARGUMENT. */
    public static final String ARGUMENT_SERVICE_ARGUMENT = "PYTHON_SERVICE_ARGUMENT";

    /** WorkRequest Data key for the script path, relative to the p4a app root. */
    public static final String ARGUMENT_WORKER_ENTRYPOINT = "PYTHON_WORK_SCRIPT";

    private String androidPrivate;
    private String androidArgument;
    private String pythonName;
    private String pythonHome;
    private String pythonPath;
    private String workerEntrypoint;

    public PythonWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);

        mWorkerContext = getApplicationContext();

        String appRoot = PythonUtil.getAppRoot(context);
        androidPrivate = appRoot;
        androidArgument = appRoot;
        pythonHome = appRoot;
        pythonPath = appRoot + ":" + appRoot + "/lib";

        File appRootFile = new File(appRoot);
        PythonUtil.unpackAsset(context, "private", appRootFile, false);
        PythonUtil.loadLibraries(
                appRootFile,
                new File(getApplicationContext().getApplicationInfo().nativeLibraryDir));
    }

    public void setPythonName(String value) {
        pythonName = value;
    }

    public void setWorkerEntrypoint(String value) {
        workerEntrypoint = value;
    }

    @Override
    public ListenableFuture<Result> startRemoteWork() {
        return CallbackToFutureAdapter.getFuture(completer -> {
            String dataArg = getInputData().getString(ARGUMENT_SERVICE_ARGUMENT);
            final String serviceArg = dataArg == null ? "" : dataArg;

            // A single generated worker can run any bundled script: the
            // WorkRequest supplies the path, and the build-time entrypoint is
            // only the fallback for the classic --worker=name:path API.
            String requestedScript = getInputData().getString(ARGUMENT_WORKER_ENTRYPOINT);
            final String script = requestedScript == null || requestedScript.isEmpty()
                    ? workerEntrypoint
                    : requestedScript;

            // There is no way to stop a running CPython thread from Java. The
            // worker process is single-use, so exiting it is the only safe
            // response to cancellation.
            completer.addCancellationListener(() -> {
                Log.i(TAG, "Exiting remote work process after cancellation");
                System.exit(0);
            }, Executors.newSingleThreadExecutor());

            Thread pythonThread = new Thread(() -> {
                int result;
                synchronized (PYTHON_LOCK) {
                    result = nativeStart(
                            androidPrivate, androidArgument, script,
                            pythonName, pythonHome, pythonPath, serviceArg);
                }
                Log.i(TAG, "Finished remote python work: " + result);
                if (result == 0) {
                    completer.set(Result.success());
                } else {
                    completer.set(Result.failure());
                }
            });
            pythonThread.setName("python_worker_thread");
            pythonThread.start();

            return TAG + " python thread";
        });
    }

    // Native part
    public static native int nativeStart(
            String androidPrivate,
            String androidArgument,
            String workerEntrypoint,
            String pythonName,
            String pythonHome,
            String pythonPath,
            String pythonServiceArgument);
}
```

## 2. NEW FILE: pythonforandroid/bootstraps/common/build/templates/Worker.tmpl.java

```java
package {{ args.package }};

import android.content.Context;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.work.Constraints;
import androidx.work.Data;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.ExistingWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.OneTimeWorkRequest;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkInfo;
import androidx.work.WorkManager;
import androidx.work.WorkerParameters;
import androidx.work.WorkRequest;

import org.kivy.android.PythonWorker;

import java.util.List;
import java.util.concurrent.TimeUnit;

public class {{ name|capitalize }}Worker extends PythonWorker {
    private static final String TAG = "{{ name|capitalize }}Worker";

    public static {{ name|capitalize }}Worker mWorker = null;

    public {{ name|capitalize }}Worker(
            @NonNull Context context,
            @NonNull WorkerParameters params) {
        super(context, params);
        setPythonName("{{ name }}");
        setWorkerEntrypoint("{{ entrypoint }}");
        mWorker = this;
    }

    /**
     * Build WorkManager input data.
     *
     * `script` is relative to the unpacked files/app directory. Passing null
     * keeps the classic --worker=name:path behaviour, while the Python Work
     * API can point this single generated worker at any bundled script.
     */
    public static Data buildInputData(String script, String serviceArgument) {
        String dataArgument = serviceArgument == null ? "" : serviceArgument;
        String dataScript = script == null || script.isEmpty()
                ? "{{ entrypoint }}"
                : script;
        Data data = new Data.Builder()
                .putString(ARGUMENT_SERVICE_ARGUMENT, dataArgument)
                .putString(ARGUMENT_WORKER_ENTRYPOINT, dataScript)
                .putString(ARGUMENT_PACKAGE_NAME, "{{ args.package }}")
                .putString(
                        ARGUMENT_CLASS_NAME,
                        {{ name|capitalize }}WorkerService.class.getName())
                .build();
        Log.v(TAG, "Request data: " + data.toString());
        return data;
    }

    public static Data buildInputData(String serviceArgument) {
        return buildInputData(null, serviceArgument);
    }

    public static WorkRequest buildWorkRequest(
            WorkRequest.Builder builder,
            String serviceArgument) {
        return builder.setInputData(buildInputData(serviceArgument)).build();
    }

    private static Constraints buildConstraints(
            boolean networkRequired,
            boolean chargingRequired) {
        Constraints.Builder builder = new Constraints.Builder();
        if (networkRequired) {
            builder.setRequiredNetworkType(NetworkType.CONNECTED);
        }
        if (chargingRequired) {
            builder.setRequiresCharging(true);
        }
        return builder.build();
    }

    /** Schedule work from Python without needing Java class literals in jnius. */
    public static void schedule(
            Context context,
            String uniqueName,
            String script,
            String serviceArgument,
            boolean periodic,
            long delaySeconds,
            long intervalMinutes,
            boolean networkRequired,
            boolean chargingRequired,
            String policy) {
        Data data = buildInputData(script, serviceArgument);
        Constraints constraints = buildConstraints(networkRequired, chargingRequired);
        WorkManager manager = WorkManager.getInstance(context);
        boolean replace = "replace".equalsIgnoreCase(policy);

        if (periodic) {
            long minutes = Math.max(15L, intervalMinutes);
            PeriodicWorkRequest request = new PeriodicWorkRequest.Builder(
                    {{ name|capitalize }}Worker.class, minutes, TimeUnit.MINUTES)
                    .setInputData(data)
                    .setConstraints(constraints)
                    .build();
            ExistingPeriodicWorkPolicy periodicPolicy = replace
                    ? ExistingPeriodicWorkPolicy.REPLACE
                    : ExistingPeriodicWorkPolicy.KEEP;
            manager.enqueueUniquePeriodicWork(uniqueName, periodicPolicy, request);
        } else {
            OneTimeWorkRequest.Builder builder = new OneTimeWorkRequest.Builder(
                    {{ name|capitalize }}Worker.class)
                    .setInputData(data)
                    .setConstraints(constraints);
            if (delaySeconds > 0) {
                builder.setInitialDelay(delaySeconds, TimeUnit.SECONDS);
            }
            ExistingWorkPolicy workPolicy = replace
                    ? ExistingWorkPolicy.REPLACE
                    : ExistingWorkPolicy.KEEP;
            manager.enqueueUniqueWork(uniqueName, workPolicy, builder.build());
        }
    }

    public static void cancel(Context context, String uniqueName) {
        WorkManager.getInstance(context).cancelUniqueWork(uniqueName);
    }

    public static void cancelAll(Context context) {
        WorkManager.getInstance(context).cancelAllWork();
    }

    public static String getStatus(Context context, String uniqueName) {
        try {
            List<WorkInfo> infos = WorkManager.getInstance(context)
                    .getWorkInfosForUniqueWork(uniqueName)
                    .get();
            if (infos == null || infos.isEmpty()) {
                return "NOT_FOUND";
            }
            return infos.get(0).getState().toString();
        } catch (Exception e) {
            Log.e(TAG, "Failed to read work status", e);
            return "ERROR: " + e.getMessage();
        }
    }
}
```

## 2. NEW FILE: pythonforandroid/bootstraps/common/build/templates/WorkerService.tmpl.java

```java
package {{ args.package }};

import android.content.Context;
import android.util.Log;

import androidx.work.Configuration;
import androidx.work.WorkManager;
import androidx.work.multiprocess.RemoteWorkerService;

import java.lang.System;

public class {{ name|capitalize }}WorkerService extends RemoteWorkerService {
    private static final String TAG = "{{ name|capitalize }}WorkerService";

    @Override
    public void onCreate() {
        try {
            Log.v(TAG, "Initializing WorkManager");
            Context context = getApplicationContext();
            Configuration configuration = new Configuration.Builder()
                    .setDefaultProcessName(context.getPackageName())
                    .build();
            WorkManager.initialize(context, configuration);
        } catch (IllegalStateException e) {
            // Already initialized by another worker in this process.
        }
        super.onCreate();
    }

    @Override
    public void onDestroy() {
        super.onDestroy();

        // p4a cannot initialise CPython twice in one process. The remote work
        // process is single-use, so let Android recreate it for the next job.
        Log.v(TAG, "Exiting worker service process");
        System.exit(0);
    }
}
```

## 3. Test app configuration (`workmanager_test/buildozer.spec`)

```ini
[app]

title = WorkManager Test
package.name = workmanagertest
package.domain = io.github.fector101
author = Fabian
version = 0.1

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,json,xml
source.exclude_dirs = bin, venv, .buildozer, tests, __pycache__, .pytest_cache

# Patched local p4a with WorkManager worker support (PR #2613 port).
p4a.source_dir = /home/fabian/Documents/widget/python-for-android
p4a.bootstrap = sdl3
requirements = python3, kivy==master
requirements.source.kivy = /home/fabian/Documents/widget/kivy
p4a.extra_args = --skip-prebuilt --worker=script:./workers/heartbeat.py

android.enable_androidx = True
android.permissions = POST_NOTIFICATIONS
android.api = 36
android.minapi = 24
android.ndk = 29
android.archs = arm64-v8a
android.release_artifact = apk

fullscreen = 0
orientation = portrait

[buildozer]
log_level = 2
warn_on_root = 1
```

Key points:
- `p4a.source_dir` points at the patched p4a checkout above.
- `p4a.extra_args = --skip-prebuilt --worker=script:./workers/heartbeat.py`
- `android.permissions = POST_NOTIFICATIONS` is required on Android 13+ or
  every `Notification.send()` is blocked by the OS.
- The local `android_notify/` package is under `source.dir` and is copied to
  `files/app/`, where it shadows the recipe copy in site-packages.

## 4. Build / test commands

From `/home/fabian/Documents/python-android/workmanager_test`:

```bash
VIRTUAL_ENV=/home/fabian/Documents/python-android/venv \
PATH="/home/fabian/Documents/python-android/venv/bin:$PATH" \
/home/fabian/Documents/python-android/venv/bin/buildozer android debug
```

Desktop tests (from `/home/fabian/Documents/python-android`):

```bash
VIRTUAL_ENV=$PWD/venv PATH="$PWD/venv/bin:$PATH" \
venv/bin/python -m pytest workmanager_test/tests -q
```

Last result: `15 passed`.

## 5. Device verification recipe

Device id `H6YPAAWSYLP7CAIN`; package `io.github.fector101.workmanagertest`.
`/tmp/opencode/workmanager_auto_main.py` replaces `files/app/main.py` to
auto-schedule `heartbeat_once` and `failing_once` 2 seconds after launch, then
prints `WORK_STATUS` after 20 seconds. Remember to delete `files/app/main.pyc`
alongside the override.

```bash
ADB="adb -s H6YPAAWSYLP7CAIN"
PKG=io.github.fector101.workmanagertest
APK=/home/fabian/Documents/python-android/workmanager_test/bin/workmanagertest-0.1-arm64-v8a-debug.apk
$ADB shell am force-stop "$PKG"
$ADB shell pm clear "$PKG"
$ADB install -r "$APK"
$ADB shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS
$ADB shell appops set --uid "$PKG" POST_NOTIFICATION allow
$ADB logcat -c
$ADB shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null
sleep 12
$ADB shell am force-stop "$PKG"
$ADB push /tmp/opencode/workmanager_auto_main.py /data/local/tmp/auto_main.py
$ADB shell "run-as $PKG sh -c 'cp /data/local/tmp/auto_main.py files/app/main.py && rm -f files/app/main.pyc'"
$ADB logcat -c
$ADB shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null
sleep 26
$ADB logcat -d -v threadtime | grep -E 'I (python|script|PythonWorker)'
$ADB shell dumpsys notification --noredact | grep -A24 "key='$PKG'"
```

Expected: `heartbeat_once SUCCEEDED`, `failing_once FAILED`, exit codes 0/3,
and an active `NotificationRecord` with title `auto from device test`.

## 6. How it works (architecture)

```
Python Work.schedule()
  -> enqueues <Name>Worker (extends PythonWorker extends RemoteListenableWorker)
     -> WorkManager IPC via androidx.work:work-multiprocess
        -> <Name>WorkerService extends RemoteWorkerService (the manifest <service>)
           -> PythonWorker.nativeStart()
              -> runpy.run_path(bundled script) in :worker_<name>
```

The `<service>` tag is AndroidX multiprocess plumbing, NOT a p4a app Service
and not `startService()` from Python. It is required for `RemoteWorkerService`.

`start.c` sets `PYTHON_SERVICE_ARGUMENT` for workers as the WorkRequest arg
payload, and `sys.p4a_worker_entrypoint` holds the resolved script path.
`sys.p4a_worker_entrypoint` is the reliable Python-side worker marker.

## 7. android_notify worker patch (in the test app copy)

`workmanager_test/android_notify/config.py`:

- Added `from_worker_file()` -> `hasattr(sys, 'p4a_worker_entrypoint')`.
- `from_service_file()` intentionally unchanged (workers also have
  `PYTHON_SERVICE_ARGUMENT`), because that branch skips permission prompts and
  intent-listener binding and posts notifications directly.
- Added `get_python_worker_context()` -> jnius
  `org.kivy.android.PythonWorker.getWorkerContext()`.
- `get_python_activity_context()` checks worker FIRST, then service, then
  activity; raises a clear RuntimeError if the Java worker context is missing.

`workmanager_test/workers/heartbeat.py` sends a notification in a
`try/except` printing `the worker file: ...`.

`workmanager_test/tests/test_android_notify_config.py` covers marker detection,
worker-context precedence, and the missing-context error.

## 8. Gotchas (hard-won)

- Changing `start.c` requires deleting `dists/workmanagertest` AND
  `bootstrap_builds/sdl3/libs/arm64-v8a/libmain.so`,
  `bootstrap_builds/sdl3/obj/local/arm64-v8a/libmain.so`, and
  `bootstrap_builds/sdl3/obj/local/arm64-v8a/objs-debug/main/start.o`;
  otherwise stale native objects get copied into the new dist.
- Changing Java/templates only needs `rm -rf dists/workmanagertest`; p4a does
  NOT refresh Java sources in an existing dist, so Gradle would compile stale
  `PythonWorker.java`.
- Worker logs use logcat tag `script`, not `python`.
- Two jobs started together call `nativeStart()` in the same process; a static
  Java lock serializes them because CPython cannot initialize twice.
- `runpy.run_path()` is required so `SystemExit(code)` becomes a return value
  and `.pyc` entrypoints work; the resolved path is passed via
  `sys.p4a_worker_entrypoint` because `os.environ` is a startup snapshot.
- `PythonWorker.java` must explicitly import `androidx.work.WorkerParameters`.
- On MIUI the appop is `POST_NOTIFICATION` (singular); `pm grant` alone did not
  unblock notifications. Both `pm grant` and
  `appops set --uid <pkg> POST_NOTIFICATION allow` were used.
- When overriding `files/app/main.py`, delete `files/app/main.pyc` too.
- Do not add a module-level `__getattr__` to Python helper modules (p4a startup
  crash footgun); use module-level lazy objects/functions.

## 9. If the working tree is lost

1. Recreate the 3 new Java/template files from section 2.
2. Apply the diffs in section 1 to the p4a checkout (or re-port PR #2613 using
   this file as the exact target state).
3. Point `workmanager_test/buildozer.spec` `p4a.source_dir` at that checkout.
4. Delete `dists/workmanagertest`, rebuild, run the 15 tests, then the device
   verification in section 5.
5. Restore the patched `android_notify/` package under `workmanager_test/` per
   section 7 (see also `.opencode/facts/workmanager-p4a-worker-api.md`).

## 10. Appendix: exact android_notify patch (diff vs original recipe copy)

```diff
--- /home/fabian/Documents/python-android/workmanager_test/.buildozer/android/platform/build-arm64-v8a/build/python-installs/workmanagertest/arm64-v8a/android_notify/config.py	2026-11-19 15:34:36.175451077 +0100
+++ /home/fabian/Documents/python-android/workmanager_test/android_notify/config.py	2026-11-19 16:19:03.755130770 +0100
@@ -8,8 +8,9 @@
 
 
 import os
+import sys
 
-__version__ = "1.62.0"
+__version__ = "1.62.0.__dev__"
 
 from .internal.logger import logger
 
@@ -19,6 +20,7 @@
 _jnius = None
 _python_activity = None
 _python_service = None
+_worker_context = None
 _activity_context = None
 _app_storage_path = None
 _package_name = None
@@ -116,7 +118,21 @@
     return _activity_class_name
 
 
+def from_worker_file():
+    """True when running inside a p4a WorkManager worker process.
+
+    start.c sets sys.p4a_worker_entrypoint only for workers, so it stays a
+    reliable marker even though workers also receive PYTHON_SERVICE_ARGUMENT
+    as the WorkRequest argument payload.
+    """
+    return hasattr(sys, 'p4a_worker_entrypoint')
+
+
 def from_service_file():
+    # WorkManager workers also have PYTHON_SERVICE_ARGUMENT in os.environ.
+    # They intentionally take this branch for permission/intent-listener
+    # handling; only the Context lookup in get_python_activity_context()
+    # needs to distinguish a worker from a real p4a service.
     return 'PYTHON_SERVICE_ARGUMENT' in os.environ
 
 
@@ -161,8 +177,19 @@
     return _python_service
 
 
+def get_python_worker_context():
+    """Android Context published by the p4a PythonWorker base class.
+
+    The generated worker calls super(context, params), so the static field is
+    set before any Python script runs in the remote :worker_* process.
+    """
+    _, autoclass = _get_jnius()
+    PythonWorker = autoclass('org.kivy.android.PythonWorker')
+    return PythonWorker.getWorkerContext()
+
+
 def get_python_activity_context():
-    global _activity_context
+    global _activity_context, _worker_context
 
     if _activity_context is not None:
         return _activity_context
@@ -173,7 +200,17 @@
         _activity_context = Context
         return _activity_context
 
-    if from_service_file():
+    if from_worker_file():
+        context = get_python_worker_context()
+        if context is None:
+            raise RuntimeError(
+                'No PythonWorker context available. The p4a PythonWorker.java '
+                'worker-context patch is required for android_notify inside '
+                'WorkManager workers.'
+            )
+        _worker_context = context
+        _activity_context = context
+    elif from_service_file():
         service = get_python_service()
         _activity_context = service.getApplication().getApplicationContext()
     else:
```

### `workmanager_test/workers/heartbeat.py`

```python
"""Example WorkManager script: logs a marker and succeeds."""

import json
import os
import sys
from datetime import datetime, timezone

print("ran")

def main() -> int:
    raw = os.environ.get("PYTHON_SERVICE_ARGUMENT", "")
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {"raw": raw}

    message = payload.get("message", "hello") if isinstance(payload, dict) else payload
    stamp = datetime.now(timezone.utc).isoformat()
    print(
        "WORKER_MARKER heartbeat pid={} time={} message={!r}".format(
            os.getpid(), stamp, message
        ),
        flush=True,
    )
    try:
        from android_notify import Notification
        Notification(title=message).send()
    except Exception as e:
        print(f'the worker file: {e}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### `workmanager_test/tests/test_android_notify_config.py`

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from android_notify import config  # noqa: E402


@pytest.fixture(autouse=True)
def reset_config_cache(monkeypatch):
    monkeypatch.setattr(config, '_activity_context', None)
    monkeypatch.setattr(config, '_worker_context', None, raising=False)
    monkeypatch.delattr(sys, 'p4a_worker_entrypoint', raising=False)
    monkeypatch.delenv('PYTHON_SERVICE_ARGUMENT', raising=False)
    # Exercise the Android branches while keeping jnius out of the way.
    monkeypatch.setattr(config, 'on_android_platform', lambda: True)


def test_worker_marker_is_independent_of_service_argument(monkeypatch):
    monkeypatch.setenv('PYTHON_SERVICE_ARGUMENT', 'payload')
    assert config.from_service_file() is True
    assert config.from_worker_file() is False

    monkeypatch.setattr(sys, 'p4a_worker_entrypoint', 'workers/heartbeat.py', raising=False)
    assert config.from_worker_file() is True
    # Workers intentionally keep the service path for permission/listener
    # handling; only the Context lookup differs.
    assert config.from_service_file() is True


def test_worker_context_wins_over_service_context(monkeypatch):
    monkeypatch.setenv('PYTHON_SERVICE_ARGUMENT', 'payload')
    monkeypatch.setattr(sys, 'p4a_worker_entrypoint', 'workers/heartbeat.py', raising=False)

    class FakePythonWorker:
        @staticmethod
        def getWorkerContext():
            return 'WORKER_CONTEXT'

    def fake_autoclass(name):
        assert name == 'org.kivy.android.PythonWorker'
        return FakePythonWorker

    monkeypatch.setattr(config, '_get_jnius', lambda: (lambda x, y: x, fake_autoclass))

    def no_service():
        raise AssertionError('services must not be used from a worker')

    monkeypatch.setattr(config, 'get_python_service', no_service)

    assert config.get_python_activity_context() == 'WORKER_CONTEXT'
    # Cached on subsequent calls, so the Java lookup happens only once.
    assert config.get_python_activity_context() == 'WORKER_CONTEXT'


def test_worker_context_missing_raises_clear_error(monkeypatch):
    monkeypatch.setattr(sys, 'p4a_worker_entrypoint', 'workers/heartbeat.py', raising=False)

    class FakePythonWorker:
        @staticmethod
        def getWorkerContext():
            return None

    monkeypatch.setattr(
        config,
        '_get_jnius',
        lambda: (lambda x, y: x, lambda name: FakePythonWorker),
    )

    with pytest.raises(RuntimeError, match='PythonWorker'):
        config.get_python_activity_context()
```

### `workmanager_test/work_manager.py` (Python Work API used by the test)

```python
"""Small Python API for p4a's WorkManager workers.

The p4a fork must be built with at least one worker, e.g.::

    --worker=script:./workers/heartbeat.py

That generates ``<package>.ScriptWorker``. A single generated worker can run
any bundled script because the script path is part of the WorkRequest input
data; ``PYTHON_SERVICE_ARGUMENT`` carries a JSON string with user arguments.
"""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

_SAFE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_MAX_SCRIPT_LENGTH = 120  # start.c ENTRYPOINT_MAXLEN is 128.


def _autoclass(name: str):
    """Import jnius only when actually running on Android."""
    try:
        from jnius import autoclass
    except Exception as exc:  # pragma: no cover - desktop fallback
        raise RuntimeError(
            "Work requires a p4a Android build with jnius available"
        ) from exc
    return autoclass(name)


def _context():
    """Return the application context, preferring p4a's activity reference."""
    try:
        from android import mActivity  # type: ignore

        if mActivity is not None:
            return mActivity.getApplicationContext()
    except Exception:
        pass

    PythonActivity = _autoclass("org.kivy.android.PythonActivity")
    return PythonActivity.mActivity.getApplicationContext()


def _worker_class(worker_name: str = "script"):
    package = str(_context().getPackageName())
    class_name = "{}.{}Worker".format(package, worker_name.capitalize())
    return _autoclass(class_name)


def _validate_worker_name(worker_name: str) -> str:
    if not isinstance(worker_name, str) or not worker_name:
        raise ValueError("worker_name must be a non-empty string")
    if not worker_name.replace("_", "").isalnum() or worker_name[0].isdigit():
        raise ValueError(
            "worker_name must be a Java identifier (letters, digits and "
            "underscores, not starting with a digit)"
        )
    return worker_name


def _validate_script(script: str) -> str:
    if not isinstance(script, str) or not script:
        raise ValueError("script must be a non-empty relative path")
    script = script.replace("\\", "/")
    if posixpath.isabs(script) or re.match(r"^[A-Za-z]:", script):
        raise ValueError("script must be relative to the p4a files/app root")
    parts = [part for part in script.split("/") if part not in ("", ".")]
    if not parts or ".." in parts:
        raise ValueError("script must not contain '..' path segments")
    if not script.lower().endswith((".py", ".pyc")):
        raise ValueError("script must end with .py or .pyc")
    normalized = "/".join(parts)
    if len(normalized) > _MAX_SCRIPT_LENGTH:
        raise ValueError(
            "script path is too long (max {} characters)".format(_MAX_SCRIPT_LENGTH)
        )
    return normalized


@dataclass
class Work:
    """Schedule a bundled Python script with WorkManager.

    Args:
        name: Unique work name used by ``schedule()``/``cancel()``/``get_info()``.
        script: Path relative to the unpacked ``files/app`` directory.
        args: JSON-serialisable value exposed to the script as
            ``PYTHON_SERVICE_ARGUMENT``.
        delay_seconds: Initial delay for one-time work.
        interval_minutes: Interval for periodic work. Omit for one-time work;
            WorkManager enforces a 15-minute minimum.
        network_required: Require a connected network.
        charging_required: Require the device to be charging.
        policy: ``"keep"`` or ``"replace"`` for an existing unique work name.
        worker_name: Name passed to p4a's ``--worker`` build argument. The
            default matches ``--worker=script:...``.
    """

    name: str
    script: str
    args: Optional[Any] = None
    delay_seconds: int = 0
    interval_minutes: Optional[int] = None
    network_required: bool = False
    charging_required: bool = False
    policy: str = "keep"
    worker_name: str = "script"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("name must be a non-empty string")
        if not _SAFE_NAME_RE.match(self.name):
            raise ValueError(
                "name may only contain letters, digits, '.', '_' and '-', "
                "and must start with a letter"
            )
        self.script = _validate_script(self.script)
        self.worker_name = _validate_worker_name(self.worker_name)
        self.delay_seconds = int(self.delay_seconds)
        if self.delay_seconds < 0:
            raise ValueError("delay_seconds must be >= 0")
        if self.interval_minutes is not None:
            self.interval_minutes = int(self.interval_minutes)
            if self.interval_minutes < 15:
                raise ValueError(
                    "WorkManager periodic work requires interval_minutes >= 15"
                )
        self.policy = self.policy.lower()
        if self.policy not in ("keep", "replace"):
            raise ValueError("policy must be 'keep' or 'replace'")

    @property
    def is_periodic(self) -> bool:
        return self.interval_minutes is not None

    def argument_json(self) -> str:
        """Return the JSON string placed in PYTHON_SERVICE_ARGUMENT."""
        try:
            return json.dumps(
                self.args if self.args is not None else {},
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Work args must be JSON-serialisable") from exc

    def schedule(self) -> "Work":
        worker = _worker_class(self.worker_name)
        worker.schedule(
            _context(),
            self.name,
            self.script,
            self.argument_json(),
            self.is_periodic,
            self.delay_seconds,
            self.interval_minutes or 0,
            bool(self.network_required),
            bool(self.charging_required),
            self.policy,
        )
        return self

    def cancel(self) -> None:
        cancel(self.name, worker_name=self.worker_name)

    def get_info(self) -> str:
        return get_info(self.name, worker_name=self.worker_name)


def schedule(name: str, script: str, **kwargs: Any) -> Work:
    """Convenience wrapper around ``Work(...).schedule()``."""
    return Work(name=name, script=script, **kwargs).schedule()


def cancel(name: str, worker_name: str = "script") -> None:
    """Cancel a unique work request by name."""
    _worker_class(_validate_worker_name(worker_name)).cancel(_context(), name)


def cancel_all(worker_name: str = "script") -> None:
    """Cancel all WorkManager work for this app."""
    _worker_class(_validate_worker_name(worker_name)).cancelAll(_context())


def get_info(name: str, worker_name: str = "script") -> str:
    """Return the first WorkInfo state for ``name`` as a string."""
    return _worker_class(_validate_worker_name(worker_name)).getStatus(
        _context(), name
    )
```
