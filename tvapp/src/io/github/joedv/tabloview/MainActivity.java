package io.github.joedv.tabloview;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.view.KeyEvent;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;

import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.URL;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * TabloView on a TV: the TV view of TabloView running on the PC (http://<PC>:7070/tv), full screen.
 * The remote's arrows and OK reach the page as key presses (no pointer); Back goes back through
 * the page and leaves the app from its first screen; Menu changes the PC's address. The PC's
 * address is found on the home network the first time, or typed.
 */
public class MainActivity extends Activity {
    static final int PORT = 7070;
    private WebView web;
    private SharedPreferences prefs;
    private AlertDialog dialog;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("tabloview", MODE_PRIVATE);
        web = new WebView(this);
        web.setBackgroundColor(Color.BLACK);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setUserAgentString(s.getUserAgentString() + " TabloViewTV/" + BuildConfig.VERSION);
        CookieManager.getInstance().setAcceptCookie(true);
        web.addJavascriptInterface(new Bridge(), "TabloViewApp");
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) cantReach();
            }
        });
        setContentView(web);
        web.requestFocus();

        String address = prefs.getString("address", null);
        if (address == null) find();
        else open(address);
    }

    private void open(String address) {
        web.loadUrl(address + "/tv");
        web.requestFocus();
    }

    private void use(String address) {
        prefs.edit().putString("address", address).apply();
        open(address);
    }

    // ---- The PC's address ----------------------------------------------------------------------

    /** Look for TabloView on the home network (every address on this TV's subnet, port 7070). */
    private void find() {
        dismiss();
        dialog = new AlertDialog.Builder(this)
                .setTitle("Finding TabloView")
                .setMessage("Looking for the computer running TabloView on your home network…")
                .setNegativeButton("Type the address", (d, w) -> ask())
                .setCancelable(false)
                .show();
        new Thread(() -> {
            List<String[]> found = scan();
            runOnUiThread(() -> {
                if (dialog == null || !dialog.isShowing()) return;  // typing the address instead
                dismiss();
                if (found.isEmpty()) notFound();
                else confirm(found);
            });
        }).start();
    }

    /** Ask before using what was found: anything on the network could answer like TabloView, and
     *  the PIN is typed into whatever it is. One computer: use it? Several: pick one. */
    private void confirm(List<String[]> found) {
        AlertDialog.Builder b = new AlertDialog.Builder(this)
                .setTitle(found.size() == 1 ? "Found TabloView" : "Found TabloView on " + found.size() + " computers")
                .setNegativeButton("Type the address", (d, w) -> ask())
                .setCancelable(false);
        if (found.size() == 1) {
            String[] f = found.get(0);
            b.setMessage(describe(f) + "\n\nIs that the computer running your TabloView?")
                    .setPositiveButton("Use it", (d, w) -> use(f[0]))
                    .setNeutralButton("Look again", (d, w) -> find());
        } else {
            String[] items = new String[found.size()];
            for (int i = 0; i < items.length; i++) items[i] = describe(found.get(i));
            b.setItems(items, (d, i) -> use(found.get(i)[0]));
        }
        dialog = b.show();
    }

    /** "On HPLAPTOP at 192.168.1.160:7070" (no name from TabloView before 1.2.9). */
    private static String describe(String[] f) {
        String where = f[0].replaceFirst("^http://", "");
        return f[1].isEmpty() ? "At " + where : "On " + f[1] + " at " + where;
    }

    private void notFound() {
        dialog = new AlertDialog.Builder(this)
                .setTitle("TabloView wasn't found")
                .setMessage("Check that the computer running TabloView is on, and that network access is turned on "
                        + "in TabloView (Device → Desktop & network on the computer).")
                .setPositiveButton("Look again", (d, w) -> find())
                .setNegativeButton("Type the address", (d, w) -> ask())
                .setCancelable(false)
                .show();
    }

    /** Type the address shown on the computer (Device → Desktop & network), e.g. 192.168.1.50. */
    private void ask() {
        dismiss();
        final EditText input = new EditText(this);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        String now = prefs.getString("address", null);
        input.setText(now != null ? now.replaceFirst("^http://", "") : "192.168.");
        input.setSelection(input.getText().length());
        dialog = new AlertDialog.Builder(this)
                .setTitle("TabloView's address")
                .setMessage("As shown on the computer under Device → Desktop & network, for example 192.168.1.50:7070")
                .setView(input)
                .setPositiveButton("Connect", (d, w) -> use(normalize(input.getText().toString())))
                .setNeutralButton("Find it for me", (d, w) -> find())
                .setCancelable(now != null)
                .show();
    }

    private void cantReach() {
        web.loadUrl("about:blank");
        dismiss();
        dialog = new AlertDialog.Builder(this)
                .setTitle("Can't reach TabloView")
                .setMessage("TabloView didn't answer at " + prefs.getString("address", "") + ". Check that the computer "
                        + "running it is on and awake, and that network access is turned on in TabloView.")
                .setPositiveButton("Try again", (d, w) -> open(prefs.getString("address", "")))
                .setNeutralButton("Find it again", (d, w) -> find())
                .setNegativeButton("Type the address", (d, w) -> ask())
                .setCancelable(false)
                .show();
    }

    private void dismiss() {
        if (dialog != null && dialog.isShowing()) dialog.dismiss();
        dialog = null;
    }

    static String normalize(String typed) {
        String a = typed.trim().replaceAll("/+$", "").replaceAll("/tv$", "").replaceAll("/+$", "");
        if (!a.matches("^[a-zA-Z]+://.*")) a = "http://" + a;
        if (!a.matches("^[a-zA-Z]+://(\\[[^\\]]+\\]|[^/]+):\\d+.*")) a = a + ":" + PORT;
        return a;
    }

    /** Every address on this TV's subnet(s) where TabloView answers its public status check, with the
     *  computer's name: {address, name}, in address order. */
    private static List<String[]> scan() {
        List<String> hosts = new ArrayList<>();
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (!(a instanceof Inet4Address) || !a.isSiteLocalAddress()) continue;
                    byte[] b = a.getAddress();
                    String prefix = (b[0] & 255) + "." + (b[1] & 255) + "." + (b[2] & 255) + ".";
                    for (int i = 1; i < 255; i++) if (i != (b[3] & 255)) hosts.add(prefix + i);
                }
            }
        } catch (Exception ignored) {
            return new ArrayList<>();
        }
        final String[][] found = new String[hosts.size()][];
        ExecutorService pool = Executors.newFixedThreadPool(48);
        for (int i = 0; i < hosts.size(); i++) {
            final int n = i;
            pool.execute(() -> {
                String name = tabloViewName(hosts.get(n));
                if (name != null) found[n] = new String[] {"http://" + hosts.get(n) + ":" + PORT, name};
            });
        }
        pool.shutdown();
        try {
            pool.awaitTermination(30, TimeUnit.SECONDS);
        } catch (InterruptedException ignored) {
        }
        pool.shutdownNow();
        List<String[]> out = new ArrayList<>();
        for (String[] f : found) if (f != null) out.add(f);
        return out;
    }

    /** The computer's name if TabloView answers there ("" from TabloView before 1.2.9), else null. */
    private static String tabloViewName(String host) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL("http://" + host + ":" + PORT + "/api/lan/status").openConnection();
            c.setConnectTimeout(700);
            c.setReadTimeout(1500);
            if (c.getResponseCode() != 200) return null;
            byte[] buf = new byte[512];
            InputStream in = c.getInputStream();
            int n = in.read(buf);
            String body = n > 0 ? new String(buf, 0, n, "UTF-8") : "";
            if (!body.contains("\"pin_set\"") || !body.contains("\"signed_in\"")) return null;
            Matcher m = Pattern.compile("\"pc\"\\s*:\\s*\"([^\"]{0,64})\"").matcher(body);
            return m.find() ? m.group(1) : "";
        } catch (Exception e) {
            return null;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    // ---- The remote ------------------------------------------------------------------------------

    @Override
    public boolean dispatchKeyEvent(KeyEvent e) {
        int k = e.getKeyCode();
        if (k == KeyEvent.KEYCODE_BACK) {
            // The page decides (close the player, back a screen); from its first screen, leave
            if (e.getAction() == KeyEvent.ACTION_UP) {
                web.evaluateJavascript("window.tvBack ? String(tvBack()) : 'none'", v -> {
                    if (v == null || v.contains("false")) finish();
                    else if (v.contains("none")) {
                        if (web.canGoBack()) web.goBack(); else finish();
                    }
                });
            }
            return true;
        }
        if (k == KeyEvent.KEYCODE_MENU || k == KeyEvent.KEYCODE_SETTINGS) {
            if (e.getAction() == KeyEvent.ACTION_UP) ask();
            return true;
        }
        return super.dispatchKeyEvent(e);
    }

    // ---- The page's side -------------------------------------------------------------------------

    /** Called by TabloView's TV view (window.TabloViewApp). */
    class Bridge {
        /** While something plays, keep the TV from dimming or starting its screensaver. */
        @JavascriptInterface
        public void setPlaying(final boolean playing) {
            runOnUiThread(() -> {
                if (playing) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            });
        }

        /** The remote's Menu button changes the address; the page can offer it too. */
        @JavascriptInterface
        public void changeAddress() {
            runOnUiThread(MainActivity.this::ask);
        }

        @JavascriptInterface
        public String version() {
            return BuildConfig.VERSION;
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        web.onPause();
        CookieManager.getInstance().flush();
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }

    @Override
    protected void onDestroy() {
        dismiss();
        web.destroy();
        super.onDestroy();
    }
}
