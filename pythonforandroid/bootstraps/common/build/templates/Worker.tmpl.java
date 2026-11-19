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
import androidx.work.WorkContinuation;
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
        return buildConstraints(networkRequired, chargingRequired, "connected");
    }

    private static Constraints buildConstraints(
            boolean networkRequired,
            boolean chargingRequired,
            String networkType) {
        return buildConstraints(networkRequired, chargingRequired, networkType,
                false, false, false);
    }

    /** Map Python's network type names, falling back to CONNECTED. */
    private static NetworkType parseNetworkType(String networkType) {
        if ("unmetered".equalsIgnoreCase(networkType)) {
            return NetworkType.UNMETERED;
        }
        if ("not_roaming".equalsIgnoreCase(networkType)) {
            return NetworkType.NOT_ROAMING;
        }
        if ("not_required".equalsIgnoreCase(networkType)) {
            return NetworkType.NOT_REQUIRED;
        }
        return NetworkType.CONNECTED;
    }

    private static Constraints buildConstraints(
            boolean networkRequired,
            boolean chargingRequired,
            String networkType,
            boolean batteryNotLow,
            boolean storageNotLow,
            boolean deviceIdle) {
        Constraints.Builder builder = new Constraints.Builder();
        if (networkRequired) {
            builder.setRequiredNetworkType(parseNetworkType(networkType));
        }
        if (chargingRequired) {
            builder.setRequiresCharging(true);
        }
        if (batteryNotLow) {
            builder.setRequiresBatteryNotLow(true);
        }
        if (storageNotLow) {
            builder.setRequiresStorageNotLow(true);
        }
        if (deviceIdle) {
            builder.setRequiresDeviceIdle(true);
        }
        return builder.build();
    }

    private static BackoffPolicy parseBackoff(String policy) {
        return "linear".equalsIgnoreCase(policy)
                ? BackoffPolicy.LINEAR
                : BackoffPolicy.EXPONENTIAL;
    }

    /** Map Python's one-time policy names, falling back to KEEP. */
    private static ExistingWorkPolicy parseOneTimePolicy(String policy) {
        if ("replace".equalsIgnoreCase(policy)) {
            return ExistingWorkPolicy.REPLACE;
        }
        if ("append".equalsIgnoreCase(policy)) {
            return ExistingWorkPolicy.APPEND;
        }
        if ("append_or_replace".equalsIgnoreCase(policy)) {
            return ExistingWorkPolicy.APPEND_OR_REPLACE;
        }
        return ExistingWorkPolicy.KEEP;
    }

    /** Map Python's periodic policy names, falling back to KEEP. */
    private static ExistingPeriodicWorkPolicy parsePeriodicPolicy(String policy) {
        if ("replace".equalsIgnoreCase(policy)) {
            return ExistingPeriodicWorkPolicy.REPLACE;
        }
        if ("update".equalsIgnoreCase(policy)) {
            return ExistingPeriodicWorkPolicy.UPDATE;
        }
        return ExistingPeriodicWorkPolicy.KEEP;
    }

    private static long backoffMillis(long seconds) {
        // WorkRequest.MIN_BACKOFF_MILLIS is 10 s and MAX_BACKOFF_MILLIS is 24 h;
        // clamp here so a bad value can never crash the app from jnius.
        return TimeUnit.SECONDS.toMillis(
                Math.max(10L, Math.min(86400L, seconds)));
    }

    private static void addTags(WorkRequest.Builder builder, JSONArray tags)
            throws JSONException {
        if (tags == null) {
            return;
        }
        for (int i = 0; i < tags.length(); i++) {
            builder.addTag(tags.getString(i));
        }
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
                policy, "exponential", 30, "[]", true, "connected");
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
        schedule(context, uniqueName, script, serviceArgument, periodic,
                delaySeconds, intervalMinutes, networkRequired, chargingRequired,
                policy, backoffPolicy, backoffDelaySeconds, "[]", true,
                "connected");
    }

    /** Schedule work with custom tags as a JSON array of strings. */
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
            long backoffDelaySeconds,
            String tagsJson) {
        schedule(context, uniqueName, script, serviceArgument, periodic,
                delaySeconds, intervalMinutes, networkRequired, chargingRequired,
                policy, backoffPolicy, backoffDelaySeconds, tagsJson, true,
                "connected");
    }

    /** Schedule work with a specific network type constraint. */
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
            long backoffDelaySeconds,
            String tagsJson,
            boolean unique,
            String networkType) {
        schedule(context, uniqueName, script, serviceArgument, periodic,
                delaySeconds, intervalMinutes, networkRequired, chargingRequired,
                policy, backoffPolicy, backoffDelaySeconds, tagsJson, unique,
                networkType, false, false, false);
    }

    /**
     * Schedule work, optionally without a unique name.
     *
     * Non-unique requests go through manager.enqueue() and carry `uniqueName`
     * as a tag, so getInfoJsonByTag()/cancelByTag() can still find them.
     */
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
            long backoffDelaySeconds,
            String tagsJson,
            boolean unique,
            String networkType,
            boolean batteryNotLow,
            boolean storageNotLow,
            boolean deviceIdle) {
        Data data = buildInputData(script, serviceArgument);
        Constraints constraints = buildConstraints(
                networkRequired, chargingRequired, networkType,
                batteryNotLow, storageNotLow, deviceIdle);
        BackoffPolicy backoff = parseBackoff(backoffPolicy);
        long backoffMillis = backoffMillis(backoffDelaySeconds);
        WorkManager manager = WorkManager.getInstance(context);

        try {
            JSONArray tags = new JSONArray(tagsJson);
            if (periodic) {
                long minutes = Math.max(15L, intervalMinutes);
                PeriodicWorkRequest.Builder builder = new PeriodicWorkRequest.Builder(
                        {{ name|capitalize }}Worker.class, minutes, TimeUnit.MINUTES)
                        .setInputData(data)
                        .setConstraints(constraints);
                // WorkManager rejects backoff criteria on idle-mode jobs.
                if (!deviceIdle) {
                    builder.setBackoffCriteria(
                            backoff, backoffMillis, TimeUnit.MILLISECONDS);
                }
                addTags(builder, tags);
                if (unique) {
                    manager.enqueueUniquePeriodicWork(
                            uniqueName, parsePeriodicPolicy(policy),
                            builder.build());
                } else {
                    builder.addTag(uniqueName);
                    manager.enqueue(builder.build());
                }
            } else {
                OneTimeWorkRequest.Builder builder = new OneTimeWorkRequest.Builder(
                        {{ name|capitalize }}Worker.class)
                        .setInputData(data)
                        .setConstraints(constraints);
                if (!deviceIdle) {
                    builder.setBackoffCriteria(
                            backoff, backoffMillis, TimeUnit.MILLISECONDS);
                }
                addTags(builder, tags);
                if (delaySeconds > 0) {
                    builder.setInitialDelay(delaySeconds, TimeUnit.SECONDS);
                }
                if (unique) {
                    manager.enqueueUniqueWork(
                            uniqueName, parseOneTimePolicy(policy),
                            builder.build());
                } else {
                    builder.addTag(uniqueName);
                    manager.enqueue(builder.build());
                }
            }
        } catch (JSONException e) {
            Log.e(TAG, "Invalid work tags", e);
        }
    }

    /**
     * Schedule a linear chain of one-time work under a single unique name.
     *
     * stepsJson is a JSON array; each step carries its own script, argument,
     * initial delay, constraints and backoff. Strings only, so jnius needs no
     * Java arrays or class literals.
     */
    public static void scheduleChain(
            Context context,
            String uniqueName,
            String policy,
            String stepsJson) {
        try {
            JSONArray steps = new JSONArray(stepsJson);
            if (steps.length() < 2) {
                Log.e(TAG, "A work chain needs at least two steps");
                return;
            }
            WorkManager manager = WorkManager.getInstance(context);
            ExistingWorkPolicy workPolicy = parseOneTimePolicy(policy);
            WorkContinuation continuation = null;
            for (int i = 0; i < steps.length(); i++) {
                JSONObject step = steps.getJSONObject(i);
                OneTimeWorkRequest.Builder builder = new OneTimeWorkRequest.Builder(
                        {{ name|capitalize }}Worker.class)
                        .setInputData(buildInputData(
                                step.optString("script", ""),
                                step.optString("argument", "")))
                        .setConstraints(buildConstraints(
                                step.optBoolean("network_required", false),
                                step.optBoolean("charging_required", false),
                                step.optString("network_type", "connected"),
                                step.optBoolean("battery_not_low", false),
                                step.optBoolean("storage_not_low", false),
                                step.optBoolean("device_idle", false)));
                if (!step.optBoolean("device_idle", false)) {
                    builder.setBackoffCriteria(
                            parseBackoff(step.optString("backoff_policy", "")),
                            backoffMillis(step.optLong(
                                    "backoff_delay_seconds", 30)),
                            TimeUnit.MILLISECONDS);
                }
                addTags(builder, step.optJSONArray("tags"));
                long delay = step.optLong("delay_seconds", 0);
                if (delay > 0) {
                    builder.setInitialDelay(delay, TimeUnit.SECONDS);
                }
                OneTimeWorkRequest request = builder.build();
                if (continuation == null) {
                    continuation = manager.beginUniqueWork(
                            uniqueName, workPolicy, request);
                } else {
                    continuation = continuation.then(request);
                }
            }
            if (continuation != null) {
                continuation.enqueue();
            }
        } catch (JSONException e) {
            Log.e(TAG, "Invalid work chain steps", e);
        }
    }

    public static void cancel(Context context, String uniqueName) {
        WorkManager.getInstance(context).cancelUniqueWork(uniqueName);
    }

    public static void cancelAll(Context context) {
        WorkManager.getInstance(context).cancelAllWork();
    }

    public static void cancelByTag(Context context, String tag) {
        WorkManager.getInstance(context).cancelAllWorkByTag(tag);
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

    private static String infosToJson(List<WorkInfo> infos) throws JSONException {
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
    }

    private static String infoError(Exception e) {
        Log.e(TAG, "Failed to read work info", e);
        return "{\"found\":false,\"error\":"
                + JSONObject.quote(String.valueOf(e.getMessage())) + "}";
    }

    /** Rich read-only work details as JSON, for the Python Work API. */
    public static String getInfoJson(Context context, String uniqueName) {
        try {
            List<WorkInfo> infos = WorkManager.getInstance(context)
                    .getWorkInfosForUniqueWork(uniqueName)
                    .get(5, TimeUnit.SECONDS);
            return infosToJson(infos);
        } catch (Exception e) {
            return infoError(e);
        }
    }

    /** All work-info rows carrying a custom (or auto-generated) tag. */
    public static String getInfoJsonByTag(Context context, String tag) {
        try {
            List<WorkInfo> infos = WorkManager.getInstance(context)
                    .getWorkInfosByTag(tag)
                    .get(5, TimeUnit.SECONDS);
            return infosToJson(infos);
        } catch (Exception e) {
            return infoError(e);
        }
    }
}
