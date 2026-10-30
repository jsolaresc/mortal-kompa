package ar.joaquin.mortalkompa;

import android.hardware.input.InputManager;
import android.os.Bundle;
import android.util.SparseIntArray;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;

import java.util.Locale;

/**
 * Mortal Kompa para Google TV: el mismo juego que la app de celular, pero
 * los joysticks Bluetooth los lee Android directamente y se los pasa al
 * juego (window.__mkPad), con el mismo mapeo que la Gamepad API del
 * navegador. El control remoto de la tele sigue funcionando como flechas
 * + OK (Enter) + Atrás (ESC).
 */
public class TvActivity extends MainActivity implements InputManager.InputDeviceListener {
    private static final int MAX_PADS = 8;
    private final SparseIntArray slotOf = new SparseIntArray();   // deviceId -> jugador
    private final int[] keyBits = new int[MAX_PADS];
    private final int[] axisBits = new int[MAX_PADS];
    private final float[] ax = new float[MAX_PADS];
    private final float[] ay = new float[MAX_PADS];
    private final String[] lastSent = new String[MAX_PADS];
    private InputManager im;

    @Override
    protected String appFlavor() { return "tv"; }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        im = (InputManager) getSystemService(INPUT_SERVICE);
        if (im != null) im.registerInputDeviceListener(this, null);
    }

    @Override
    protected void onDestroy() {
        if (im != null) im.unregisterInputDeviceListener(this);
        super.onDestroy();
        // que no quede nada sonando
        if (web != null) {
            try { web.loadUrl("about:blank"); web.destroy(); } catch (Exception e) { /* nada */ }
            web = null;
        }
    }

    // botón Inicio de la tele / otra app adelante: se corta la música
    @Override
    protected void onPause() {
        if (web != null) web.evaluateJavascript("window.__mkPause&&window.__mkPause(true)", null);
        super.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) web.evaluateJavascript("window.__mkPause&&window.__mkPause(false)", null);
    }

    // "Cerrar" del menú o Atrás en el menú principal: cierra del todo
    // (también se saca de las apps recientes)
    @Override
    public void finish() {
        if (web != null) web.evaluateJavascript("window.__mkPause&&window.__mkPause(true)", null);
        finishAndRemoveTask();
    }

    private static boolean isPad(int source) {
        return (source & InputDevice.SOURCE_GAMEPAD) == InputDevice.SOURCE_GAMEPAD
                || (source & InputDevice.SOURCE_JOYSTICK) == InputDevice.SOURCE_JOYSTICK;
    }

    // botón de Android -> índice "standard" de la Gamepad API
    private static int buttonFor(int keyCode) {
        switch (keyCode) {
            case KeyEvent.KEYCODE_BUTTON_A: return 0;
            case KeyEvent.KEYCODE_BUTTON_B: return 1;
            case KeyEvent.KEYCODE_BUTTON_X: return 2;
            case KeyEvent.KEYCODE_BUTTON_Y: return 3;
            case KeyEvent.KEYCODE_BUTTON_L1: return 4;
            case KeyEvent.KEYCODE_BUTTON_R1: return 5;
            case KeyEvent.KEYCODE_BUTTON_L2: return 6;
            case KeyEvent.KEYCODE_BUTTON_R2: return 7;
            case KeyEvent.KEYCODE_BUTTON_SELECT: return 8;
            case KeyEvent.KEYCODE_BUTTON_START: return 9;
            case KeyEvent.KEYCODE_BUTTON_THUMBL: return 10;
            case KeyEvent.KEYCODE_BUTTON_THUMBR: return 11;
            case KeyEvent.KEYCODE_DPAD_UP: return 12;
            case KeyEvent.KEYCODE_DPAD_DOWN: return 13;
            case KeyEvent.KEYCODE_DPAD_LEFT: return 14;
            case KeyEvent.KEYCODE_DPAD_RIGHT: return 15;
            case KeyEvent.KEYCODE_BUTTON_MODE: return 16;
            default: return -1;
        }
    }

    // jugador 1 = primer joystick que se usa, jugador 2 = el segundo...
    private int slotFor(int deviceId) {
        int s = slotOf.get(deviceId, -1);
        if (s >= 0) return s;
        for (int i = 0; i < MAX_PADS; i++) {
            if (slotOf.indexOfValue(i) < 0) { slotOf.put(deviceId, i); return i; }
        }
        return -1;
    }

    private void send(int s) {
        String js = String.format(Locale.US, "window.__mkPad&&window.__mkPad(%d,%d,%.2f,%.2f)",
                s, keyBits[s] | axisBits[s], ax[s], ay[s]);
        if (js.equals(lastSent[s])) return;
        lastSent[s] = js;
        if (web != null) web.evaluateJavascript(js, null);
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent e) {
        int kc = e.getKeyCode();
        if (isPad(e.getSource())) {
            int b = buttonFor(kc);
            if (b >= 0) {
                int s = slotFor(e.getDeviceId());
                if (s < 0) return true;
                if (e.getAction() == KeyEvent.ACTION_DOWN) keyBits[s] |= (1 << b);
                else if (e.getAction() == KeyEvent.ACTION_UP) keyBits[s] &= ~(1 << b);
                send(s);
                return true;   // no llega como tecla: si no, se movería dos veces
            }
        }
        // control remoto: OK = Enter (confirma en los menús)
        if (kc == KeyEvent.KEYCODE_DPAD_CENTER) {
            KeyEvent n = new KeyEvent(e.getDownTime(), e.getEventTime(), e.getAction(), KeyEvent.KEYCODE_ENTER,
                    e.getRepeatCount(), e.getMetaState(), e.getDeviceId(), e.getScanCode(), e.getFlags(), e.getSource());
            return super.dispatchKeyEvent(n);
        }
        return super.dispatchKeyEvent(e);
    }

    @Override
    public boolean dispatchGenericMotionEvent(MotionEvent e) {
        if (isPad(e.getSource()) && e.getAction() == MotionEvent.ACTION_MOVE) {
            int s = slotFor(e.getDeviceId());
            if (s < 0) return true;
            ax[s] = e.getAxisValue(MotionEvent.AXIS_X);
            ay[s] = e.getAxisValue(MotionEvent.AXIS_Y);
            float hx = e.getAxisValue(MotionEvent.AXIS_HAT_X), hy = e.getAxisValue(MotionEvent.AXIS_HAT_Y);
            float lt = Math.max(e.getAxisValue(MotionEvent.AXIS_LTRIGGER), e.getAxisValue(MotionEvent.AXIS_BRAKE));
            float rt = Math.max(e.getAxisValue(MotionEvent.AXIS_RTRIGGER), e.getAxisValue(MotionEvent.AXIS_GAS));
            int bits = 0;
            if (hy < -0.5f) bits |= 1 << 12;
            if (hy > 0.5f) bits |= 1 << 13;
            if (hx < -0.5f) bits |= 1 << 14;
            if (hx > 0.5f) bits |= 1 << 15;
            if (lt > 0.5f) bits |= 1 << 6;
            if (rt > 0.5f) bits |= 1 << 7;
            axisBits[s] = bits;
            send(s);
            return true;
        }
        return super.dispatchGenericMotionEvent(e);
    }

    // joystick apagado / desconectado: se libera su lugar
    @Override
    public void onInputDeviceRemoved(int deviceId) {
        int s = slotOf.get(deviceId, -1);
        if (s < 0) return;
        slotOf.delete(deviceId);
        keyBits[s] = 0; axisBits[s] = 0; ax[s] = 0; ay[s] = 0; lastSent[s] = null;
        if (web != null) web.evaluateJavascript("window.__mkPad&&window.__mkPad(" + s + ",-1,0,0)", null);
    }

    @Override public void onInputDeviceAdded(int deviceId) { }
    @Override public void onInputDeviceChanged(int deviceId) { }
}
