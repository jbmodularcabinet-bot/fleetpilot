# Driver foundation

Routes `/driver` and `/driver/profile` require `driver_app.view`. An owner cannot use them by changing a URL. A driver opening a desktop administration route returns to driver home; the API independently denies user administration.

Home follows the approved reference: branding, greeting, current-trip placeholder, disabled large action, disabled Navigate/Call Dispatcher/Report Problem shortcuts, next-trip placeholder, and Home/Trips/Expenses/Alerts/Profile bottom navigation. Profile displays actual authorized identity and organization data and permits logout.

A web manifest establishes the future PWA entry point. Installability, approved standalone icons, service worker, offline queue, uploads, GPS and movement safety enforcement are not claimed or implemented. No authenticated data is cached offline. Operational driver flows start in their assigned batches.
