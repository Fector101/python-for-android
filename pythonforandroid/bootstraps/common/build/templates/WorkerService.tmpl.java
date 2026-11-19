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
