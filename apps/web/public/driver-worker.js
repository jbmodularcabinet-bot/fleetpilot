/* Only public boot/static resources enter CacheStorage. Private API/HTML never does. */
importScripts('/driver-sync.js');
const CACHE = 'fleetpilot-driver-shell-v1';
const SHELL = '/driver-offline';
self.addEventListener('install', event => {
  event.waitUntil((async()=>{
    const cache=await caches.open(CACHE);
    const response=await fetch(SHELL,{credentials:'omit',cache:'reload'});
    if(!response.ok)throw new Error('Offline shell unavailable');
    await cache.put(SHELL,response.clone());
    const html=await response.text();
    const urls=[...new Set([...html.matchAll(/(?:src|href)="(\/_next\/static\/[^"?]+)[^"]*"/g)].map(m=>m[1]))];
    await cache.addAll([...urls,'/brand-reference.png','/driver-icon.svg']);
    for(const url of urls.filter(u=>u.endsWith('.css'))){
      const css=await (await cache.match(url)).text();
      const fonts=[...css.matchAll(/url\(["']?([^)'"\s]+\.woff2?)["']?\)/g)].map(m=>new URL(m[1],new URL(url,self.location.origin)).href);
      await cache.addAll([...new Set(fonts.filter(u=>u.startsWith(self.location.origin+'/_next/static/')))]);
    }
    // Do not skipWaiting: an existing app/queue continues with its compatible worker.
  })());
});
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(url.origin!==self.location.origin || event.request.method!=='GET' || url.pathname.startsWith('/api/'))return;
  if(event.request.mode==='navigate' && (url.pathname==='/driver'||url.pathname.startsWith('/driver/'))){
    // A connection can stall without rejecting; keep the saved shell reachable.
    event.respondWith(fetch(event.request,{signal:AbortSignal.timeout(10000)}).catch(async()=>{
      const shell=await (await caches.open(CACHE)).match(SHELL);
      return shell || Response.error();
    }));return;
  }
  if(url.pathname.startsWith('/_next/static/') || ['/brand-reference.png','/driver-icon.svg'].includes(url.pathname)){
    event.respondWith((async()=>{
      const cache=await caches.open(CACHE);const saved=await cache.match(event.request);if(saved)return saved;
      const response=await fetch(event.request);if(response.ok)await cache.put(event.request,response.clone());return response;
    })());
  }
});
self.addEventListener('sync',event=>{
  if(event.tag==='fleetpilot-driver-sync')event.waitUntil(FleetPilotSync.sync().then(async()=>{
    for(const client of await self.clients.matchAll())client.postMessage({type:'fleetpilot-sync'});
  }));
});
