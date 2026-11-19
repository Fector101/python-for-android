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
