package {{ args.package }};

import android.content.Context;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.work.BackoffPolicy;
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

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.kivy.android.PythonWorker;

import java.util.List;
import java.util.Map;
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
        schedule(context, uniqueName, script, serviceArgument, periodic,
                delaySeconds, intervalMinutes, networkRequired, chargingRequired,
                policy, "exponential", 30);
    }

    /** Schedule work with explicit retry backoff criteria. */
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
            String policy,
            String backoffPolicy,
            long backoffDelaySeconds) {
        Data data = buildInputData(script, serviceArgument);
        Constraints constraints = buildConstraints(networkRequired, chargingRequired);
        BackoffPolicy backoff = "linear".equalsIgnoreCase(backoffPolicy)
                ? BackoffPolicy.LINEAR
                : BackoffPolicy.EXPONENTIAL;
        // WorkRequest.MIN_BACKOFF_MILLIS is 10 s and MAX_BACKOFF_MILLIS is 24 h;
        // clamp here so a bad value can never crash the app from jnius.
        long backoffMillis = TimeUnit.SECONDS.toMillis(
                Math.max(10L, Math.min(86400L, backoffDelaySeconds)));
        WorkManager manager = WorkManager.getInstance(context);
        boolean replace = "replace".equalsIgnoreCase(policy);

        if (periodic) {
            long minutes = Math.max(15L, intervalMinutes);
            PeriodicWorkRequest request = new PeriodicWorkRequest.Builder(
                    {{ name|capitalize }}Worker.class, minutes, TimeUnit.MINUTES)
                    .setInputData(data)
                    .setConstraints(constraints)
                    .setBackoffCriteria(backoff, backoffMillis, TimeUnit.MILLISECONDS)
                    .build();
            ExistingPeriodicWorkPolicy periodicPolicy = replace
                    ? ExistingPeriodicWorkPolicy.REPLACE
                    : ExistingPeriodicWorkPolicy.KEEP;
            manager.enqueueUniquePeriodicWork(uniqueName, periodicPolicy, request);
        } else {
            OneTimeWorkRequest.Builder builder = new OneTimeWorkRequest.Builder(
                    {{ name|capitalize }}Worker.class)
                    .setInputData(data)
                    .setConstraints(constraints)
                    .setBackoffCriteria(backoff, backoffMillis, TimeUnit.MILLISECONDS);
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

    private static Object jsonValue(Object value) throws JSONException {
        if (value == null) {
            return JSONObject.NULL;
        }
        if (value.getClass().isArray()) {
            JSONArray array = new JSONArray();
            int length = java.lang.reflect.Array.getLength(value);
            for (int i = 0; i < length; i++) {
                array.put(jsonValue(java.lang.reflect.Array.get(value, i)));
            }
            return array;
        }
        if (value instanceof Number || value instanceof Boolean
                || value instanceof String) {
            return value;
        }
        return String.valueOf(value);
    }

    private static JSONObject dataToJson(Data data) throws JSONException {
        JSONObject result = new JSONObject();
        if (data == null) {
            return result;
        }
        for (Map.Entry<String, Object> entry : data.getKeyValueMap().entrySet()) {
            result.put(entry.getKey(), jsonValue(entry.getValue()));
        }
        return result;
    }

    private static String stopReasonName(int reason) {
        switch (reason) {
            case WorkInfo.STOP_REASON_NOT_STOPPED:
                return "NOT_STOPPED";
            case WorkInfo.STOP_REASON_UNKNOWN:
                return "UNKNOWN";
            case WorkInfo.STOP_REASON_CANCELLED_BY_APP:
                return "CANCELLED_BY_APP";
            case WorkInfo.STOP_REASON_PREEMPT:
                return "PREEMPT";
            case WorkInfo.STOP_REASON_TIMEOUT:
                return "TIMEOUT";
            case WorkInfo.STOP_REASON_DEVICE_STATE:
                return "DEVICE_STATE";
            case WorkInfo.STOP_REASON_CONSTRAINT_BATTERY_NOT_LOW:
                return "CONSTRAINT_BATTERY_NOT_LOW";
            case WorkInfo.STOP_REASON_CONSTRAINT_CHARGING:
                return "CONSTRAINT_CHARGING";
            case WorkInfo.STOP_REASON_CONSTRAINT_CONNECTIVITY:
                return "CONSTRAINT_CONNECTIVITY";
            case WorkInfo.STOP_REASON_CONSTRAINT_DEVICE_IDLE:
                return "CONSTRAINT_DEVICE_IDLE";
            case WorkInfo.STOP_REASON_CONSTRAINT_STORAGE_NOT_LOW:
                return "CONSTRAINT_STORAGE_NOT_LOW";
            case WorkInfo.STOP_REASON_QUOTA:
                return "QUOTA";
            case WorkInfo.STOP_REASON_BACKGROUND_RESTRICTION:
                return "BACKGROUND_RESTRICTION";
            case WorkInfo.STOP_REASON_APP_STANDBY:
                return "APP_STANDBY";
            case WorkInfo.STOP_REASON_USER:
                return "USER";
            case WorkInfo.STOP_REASON_SYSTEM_PROCESSING:
                return "SYSTEM_PROCESSING";
            case WorkInfo.STOP_REASON_ESTIMATED_APP_LAUNCH_TIME_CHANGED:
                return "ESTIMATED_APP_LAUNCH_TIME_CHANGED";
            default:
                return "STOP_REASON_" + reason;
        }
    }

    /** Rich read-only work details as JSON, for the Python Work API. */
    public static String getInfoJson(Context context, String uniqueName) {
        try {
            List<WorkInfo> infos = WorkManager.getInstance(context)
                    .getWorkInfosForUniqueWork(uniqueName)
                    .get(5, TimeUnit.SECONDS);
            JSONObject root = new JSONObject();
            JSONArray rows = new JSONArray();
            root.put("found", infos != null && !infos.isEmpty());
            if (infos != null) {
                for (WorkInfo info : infos) {
                    JSONObject row = new JSONObject();
                    row.put("id", info.getId().toString());
                    row.put("state", info.getState().toString());
                    row.put("runAttemptCount", info.getRunAttemptCount());
                    row.put("generation", info.getGeneration());
                    row.put("initialDelayMillis", info.getInitialDelayMillis());
                    row.put("nextScheduleTimeMillis",
                            info.getNextScheduleTimeMillis());
                    int stopReason = info.getStopReason();
                    row.put("stopReason", stopReason);
                    row.put("stopReasonName", stopReasonName(stopReason));
                    JSONArray tags = new JSONArray();
                    for (String tag : info.getTags()) {
                        tags.put(tag);
                    }
                    row.put("tags", tags);
                    row.put("output", dataToJson(info.getOutputData()));
                    row.put("progress", dataToJson(info.getProgress()));
                    rows.put(row);
                }
            }
            root.put("infos", rows);
            return root.toString();
        } catch (Exception e) {
            Log.e(TAG, "Failed to read work info", e);
            return "{\"found\":false,\"error\":"
                    + JSONObject.quote(String.valueOf(e.getMessage())) + "}";
        }
    }
}
