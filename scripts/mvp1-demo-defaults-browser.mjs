import fs from "node:fs/promises";
import path from "node:path";
import assert from "node:assert/strict";
import { fileURLToPath, pathToFileURL } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const oldRoot = "C:/Users/User/Documents/ChatGPT/FleetPilot";
const { chromium } = await import(
  pathToFileURL(path.join(oldRoot, "node_modules/playwright/index.mjs")).href
);
const args = process.argv.slice(2);
const base = args[0] ?? "http://localhost:3500";
const label = args[1] ?? "demo-local";
const authorized = JSON.parse(
  await fs.readFile(
    path.join(root, ".runtime/batch16/authorized-demo-origin.json"),
    "utf8",
  ),
);
assert(
  [authorized.origin, authorized.local_origin].includes(base),
  "Credential use is restricted to the authorized local demo origins",
);
const output = path.join(root, ".runtime/batch16", label);
await fs.mkdir(output, { recursive: true });
const env = Object.fromEntries(
  (await fs.readFile(path.join(oldRoot, ".env"), "utf8"))
    .split(/\r?\n/)
    .filter((l) => l.includes("=") && !l.trim().startsWith("#"))
    .map((l) => {
      const i = l.indexOf("=");
      return [
        l.slice(0, i).trim(),
        l
          .slice(i + 1)
          .trim()
          .replace(/^["']|["']$/g, ""),
      ];
    }),
);
assert(env.DEMO_PASSWORD, "Existing local demo credential is required");
const checks = [];
const browser = await chromium.launch({channel:"chrome", headless:true});
try {
  const context = await browser.newContext({viewport:{width:1440,height:1050}});
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", error=>errors.push(error.message));
  async function populated(name) {
    await page.locator(".reporting-scope").waitFor();
    assert((await page.locator(".reporting-scope").innerText()).includes("4 trips"), name + ": sample cohort must be visible without manual dates");
    assert(await page.locator(".reporting-demo-banner").isVisible());
    checks.push({name,status:"PASS"}); console.log("PASS "+name);
  }
  await page.goto(base+"/login");
  await page.getByLabel("Email address").fill("carlo@example.com");
  await page.getByLabel("Password",{exact:true}).fill(env.DEMO_PASSWORD);
  await page.getByRole("button",{name:"Sign in",exact:true}).click();
  await page.waitForURL(/\/dashboard(?:\?|$)/);
  await populated("Login opens populated sample dashboard automatically");
  assert.equal(await page.getByTestId("Contribution").innerText(),"₱33,750.00");
  await page.getByRole("navigation",{name:"Main navigation"}).getByRole("link",{name:"Intelligence",exact:true}).click();
  await page.waitForURL(/\/intelligence(?:\?|$)/);
  await populated("Sidebar Intelligence opens populated sample findings");
  await page.getByRole("navigation",{name:"Main navigation"}).getByRole("link",{name:"Reports",exact:true}).click();
  await page.waitForURL(/\/reports\/executive-contribution/);
  await populated("Sidebar Reports opens populated executive report");
  const reports=[["executive-contribution","Executive Contribution"],["trip-contribution","Trip Contribution"],["customer-contribution","Customer Contribution"],["direct-costs","Direct Cost Analysis"],["financial-exceptions","Financial Exceptions"],["cash-advances","Cash Advance & Settlement"]];
  for (const [key,title] of reports) {
    await page.goto(base+"/reports/"+key);
    await populated("Bare URL automatically loads samples: "+title);
    await page.screenshot({path:path.join(output,key+".png"),fullPage:true});
  }
  await page.goto(base+"/intelligence");
  await populated("Bare Intelligence URL needs no query or date selection");
  await page.reload();
  await populated("Reload retains sample data");
  await page.getByRole("button",{name:"Business records / reset",exact:true}).click();
  await page.waitForURL(/dataset=business/);
  await page.locator(".reporting-scope").waitFor();
  assert.equal(await page.locator(".reporting-demo-banner").count(),0);
  await page.reload();
  await page.locator(".reporting-scope").waitFor();
  assert.equal(await page.locator(".reporting-demo-banner").count(),0);
  checks.push({name:"Explicit business selection remains business across reload",status:"PASS"});
  const business=await page.request.get(base+"/api/v1/reports/trip-contribution?dataset=business&date_from=2026-09-21&date_to=2026-09-24");
  const businessData=await business.json();
  assert.equal(businessData.scope.synthetic,false);
  assert.equal(businessData.summary.trip_count,0);
  checks.push({name:"Business reporting still excludes all four samples",status:"PASS"});
  await page.setViewportSize({width:390,height:844});
  await page.goto(base+"/intelligence");
  await populated("Mobile Intelligence defaults to sample records");
  assert(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth+2));
  await page.screenshot({path:path.join(output,"mobile-intelligence.png"),fullPage:true});
  assert.deepEqual(errors,[]);
  checks.push({name:"No unhandled browser errors",status:"PASS"});
  const result={base_url:base,passed:checks.length,failed:0,checks,source_records_changed:false,checked_at:new Date().toISOString()};
  await fs.writeFile(path.join(output,"result.json"),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
} catch(error) {
  await fs.writeFile(path.join(output,"result.json"),JSON.stringify({passed:checks.length,failed:1,error:error.message,checks},null,2));
  console.error(error.message); process.exitCode=1;
} finally {await browser.close();}
