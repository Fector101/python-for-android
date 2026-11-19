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
