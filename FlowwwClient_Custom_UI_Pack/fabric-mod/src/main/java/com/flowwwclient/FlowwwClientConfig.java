package com.flowwwclient;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.fabricmc.loader.api.FabricLoader;

import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/** Shared, simple config format also written by the desktop panel. */
public final class FlowwwClientConfig {
    private static final Path CONFIG_PATH = FabricLoader.getInstance().getConfigDir().resolve("flowwwclient.json");

    public static boolean nametagEnabled = true;
    public static String nametagSymbol = "ঌ";
    public static String nametagColor = "#E53945";
    public static double nametagScale = 1.0;
    public static boolean motionBlurEnabled = false;
    public static double motionBlurStrength = 0.35;

    private FlowwwClientConfig() {}

    public static void load() {
        if (!Files.exists(CONFIG_PATH)) {
            save();
            return;
        }
        try (Reader reader = Files.newBufferedReader(CONFIG_PATH, StandardCharsets.UTF_8)) {
            JsonObject obj = JsonParser.parseReader(reader).getAsJsonObject();
            nametagEnabled = getBoolean(obj, "nametagEnabled", nametagEnabled);
            nametagSymbol = getString(obj, "nametagSymbol", nametagSymbol);
            nametagColor = getString(obj, "nametagColor", nametagColor);
            nametagScale = clamp(getDouble(obj, "nametagScale", nametagScale), 0.6, 1.8);
            motionBlurEnabled = getBoolean(obj, "motionBlurEnabled", motionBlurEnabled);
            motionBlurStrength = clamp(getDouble(obj, "motionBlurStrength", motionBlurStrength), 0.0, 1.0);
        } catch (Exception exception) {
            System.err.println("[FlowwwClient] Could not read config; defaults will be used: " + exception.getMessage());
        }
    }

    public static void save() {
        JsonObject obj = new JsonObject();
        // Preserve extra fields written by the desktop panel (such as its module list).
        if (Files.exists(CONFIG_PATH)) {
            try (Reader reader = Files.newBufferedReader(CONFIG_PATH, StandardCharsets.UTF_8)) {
                obj = JsonParser.parseReader(reader).getAsJsonObject();
            } catch (Exception ignored) {
                obj = new JsonObject();
            }
        }
        obj.addProperty("schemaVersion", 1);
        obj.addProperty("nametagEnabled", nametagEnabled);
        obj.addProperty("nametagSymbol", nametagSymbol == null || nametagSymbol.isBlank() ? "ঌ" : nametagSymbol);
        obj.addProperty("nametagColor", validColor(nametagColor) ? nametagColor : "#E53945");
        obj.addProperty("nametagScale", clamp(nametagScale, 0.6, 1.8));
        obj.addProperty("motionBlurEnabled", motionBlurEnabled);
        obj.addProperty("motionBlurStrength", clamp(motionBlurStrength, 0.0, 1.0));
        try {
            Files.createDirectories(CONFIG_PATH.getParent());
            try (Writer writer = Files.newBufferedWriter(CONFIG_PATH, StandardCharsets.UTF_8)) {
                com.google.gson.GsonBuilder builder = new com.google.gson.GsonBuilder().setPrettyPrinting().disableHtmlEscaping();
                writer.write(builder.create().toJson(obj));
            }
        } catch (IOException exception) {
            System.err.println("[FlowwwClient] Could not save config: " + exception.getMessage());
        }
    }

    private static boolean getBoolean(JsonObject obj, String key, boolean fallback) {
        try { return obj.has(key) ? obj.get(key).getAsBoolean() : fallback; }
        catch (RuntimeException ignored) { return fallback; }
    }

    private static double getDouble(JsonObject obj, String key, double fallback) {
        try { return obj.has(key) ? obj.get(key).getAsDouble() : fallback; }
        catch (RuntimeException ignored) { return fallback; }
    }

    private static String getString(JsonObject obj, String key, String fallback) {
        try { return obj.has(key) ? obj.get(key).getAsString() : fallback; }
        catch (RuntimeException ignored) { return fallback; }
    }

    public static int colorAsRgb() {
        try { return Integer.parseInt(nametagColor.replace("#", ""), 16) & 0xFFFFFF; }
        catch (RuntimeException ignored) { return 0xE53945; }
    }

    private static boolean validColor(String value) {
        if (value == null || !value.matches("#[0-9a-fA-F]{6}")) return false;
        return true;
    }

    public static double clamp(double value, double min, double max) {
        return Math.max(min, Math.min(max, value));
    }
}
