# Walkthrough

1. Open the landing page.
2. Type a job, or click **Get Started**.
3. Create a real account (`/signup`) or **Log In**.
4. After authentication, a pending landing job becomes your Agent. Otherwise **Create Agent** on Agent Home (name + job), then message what to watch.
5. Message the job. Work starts in the thread and the Agent keeps watch.
6. **Check now** uses the same `LensRuntime` as Celery Beat. Routine **Run now** honors the trigger against live CMC.
7. Open a Result artifact or `/jobs/<id>` execution trace. If a true Event fired, open the receipt and CMC evidence.
8. Settings: connect Telegram if you want routine triggers and job completions on your phone.

There is no demo account and no `/enter-demo`. Monitoring is every 15 minutes, never real-time.
