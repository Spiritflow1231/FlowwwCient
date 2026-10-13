package com.flowwwclient;

import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.widget.ButtonWidget;
import net.minecraft.client.gui.widget.SliderWidget;
import net.minecraft.client.gui.widget.TextFieldWidget;
import net.minecraft.text.Text;

import java.util.List;
import java.util.function.DoubleConsumer;

public final class FlowwwSettingsScreen extends Screen {
    private final Screen parent;
    private static final List<String> COLORS = List.of("#E53945", "#FF4655", "#F4F5F7", "#55D6BE", "#A78BFA", "#F59E0B");
    private TextFieldWidget symbolField;
    private ButtonWidget nametagToggle;
    private ButtonWidget blurToggle;
    private int colorIndex;

    public FlowwwSettingsScreen(Screen parent) {
        super(Text.literal("FlowwwClient Settings"));
        this.parent = parent;
        colorIndex = Math.max(0, COLORS.indexOf(FlowwwClientConfig.nametagColor.toUpperCase()));
    }

    @Override
    protected void init() {
        int panelWidth = Math.min(520, this.width - 32);
        int left = (this.width - panelWidth) / 2;
        int contentWidth = panelWidth - 36;
        int y = Math.max(96, this.height / 2 - 130);

        nametagToggle = ButtonWidget.builder(nametagLabel(), button -> {
            FlowwwClientConfig.nametagEnabled = !FlowwwClientConfig.nametagEnabled;
            button.setMessage(nametagLabel());
            FlowwwClientConfig.save();
        }).dimensions(left + 18, y, contentWidth, 20).build();
        addDrawableChild(nametagToggle);
        y += 30;

        symbolField = new TextFieldWidget(textRenderer, left + 18, y, contentWidth - 88, 20, Text.literal("Name-tag symbol"));
        symbolField.setMaxLength(8);
        symbolField.setText(FlowwwClientConfig.nametagSymbol);
        addDrawableChild(symbolField);
        addDrawableChild(ButtonWidget.builder(Text.literal("Save"), button -> {
            String value = symbolField.getText().strip();
            FlowwwClientConfig.nametagSymbol = value.isEmpty() ? "ঌ" : value;
            FlowwwClientConfig.save();
            button.setMessage(Text.literal("Saved"));
        }).dimensions(left + panelWidth - 82, y, 64, 20).build());
        y += 30;

        addDrawableChild(ButtonWidget.builder(colorLabel(), button -> {
            colorIndex = (colorIndex + 1) % COLORS.size();
            FlowwwClientConfig.nametagColor = COLORS.get(colorIndex);
            button.setMessage(colorLabel());
            FlowwwClientConfig.save();
        }).dimensions(left + 18, y, contentWidth, 20).build());
        y += 30;

        addDrawableChild(new DecimalSlider(left + 18, y, contentWidth, 20, "Name-tag scale", FlowwwClientConfig.nametagScale, 0.6, 1.8,
                value -> { FlowwwClientConfig.nametagScale = value; FlowwwClientConfig.save(); }));
        y += 36;

        blurToggle = ButtonWidget.builder(blurLabel(), button -> {
            FlowwwClientConfig.motionBlurEnabled = !FlowwwClientConfig.motionBlurEnabled;
            button.setMessage(blurLabel());
            FlowwwClientConfig.save();
        }).dimensions(left + 18, y, contentWidth, 20).build();
        addDrawableChild(blurToggle);
        y += 30;

        addDrawableChild(new DecimalSlider(left + 18, y, contentWidth, 20, "Motion blur strength (saved setting only)", FlowwwClientConfig.motionBlurStrength, 0.0, 1.0,
                value -> { FlowwwClientConfig.motionBlurStrength = value; FlowwwClientConfig.save(); }));
        y += 40;

        addDrawableChild(ButtonWidget.builder(Text.literal("Done"), button -> close())
                .dimensions(left + 18, Math.min(this.height - 38, y), contentWidth, 22).build());
    }

    private Text nametagLabel() {
        return Text.literal("Name-tag marker: " + (FlowwwClientConfig.nametagEnabled ? "ON" : "OFF"));
    }

    private Text blurLabel() {
        return Text.literal("Motion Blur setting: " + (FlowwwClientConfig.motionBlurEnabled ? "ON" : "OFF") + "  (effect not included)");
    }

    private Text colorLabel() {
        return Text.literal("Marker color: " + FlowwwClientConfig.nametagColor + "  •  click to cycle");
    }

    @Override
    public void render(DrawContext context, int mouseX, int mouseY, float delta) {
        this.renderBackground(context, mouseX, mouseY, delta);
        int w = Math.min(520, this.width - 24);
        int x = (this.width - w) / 2;
        int top = Math.max(30, this.height / 2 - 180);
        context.fill(x, top, x + w, Math.min(this.height - 12, top + 345), 0xF2111419);
        context.fill(x, top, x + w, top + 3, 0xFFE53945);
        context.drawCenteredTextWithShadow(textRenderer, Text.literal("ঌ  FlowwwClient"), this.width / 2, top + 13, 0xFFF4F5F7);
        context.drawCenteredTextWithShadow(textRenderer, Text.literal("CLIENT SETTINGS  •  RIGHT SHIFT"), this.width / 2, top + 30, 0xFF969DA8);
        super.render(context, mouseX, mouseY, delta);
        context.drawCenteredTextWithShadow(textRenderer, Text.literal("Motion Blur is saved as a setting only in this starter."), this.width / 2, Math.min(this.height - 10, top + 325), 0xFFFFA6AF);
    }

    @Override
    public void close() {
        FlowwwClientConfig.save();
        if (client != null) client.setScreen(parent);
    }

    private static final class DecimalSlider extends SliderWidget {
        private final String label;
        private final double min;
        private final double max;
        private final DoubleConsumer onChanged;

        private DecimalSlider(int x, int y, int width, int height, String label, double actual, double min, double max, DoubleConsumer onChanged) {
            super(x, y, width, height, Text.empty(), (FlowwwClientConfig.clamp(actual, min, max) - min) / (max - min));
            this.label = label;
            this.min = min;
            this.max = max;
            this.onChanged = onChanged;
            updateMessage();
            applyValue();
        }

        private double actualValue() { return min + value * (max - min); }

        @Override
        protected void updateMessage() {
            setMessage(Text.literal(label + ": " + String.format(java.util.Locale.ROOT, "%.2f", actualValue())));
        }

        @Override
        protected void applyValue() {
            onChanged.accept(Math.round(actualValue() * 100.0) / 100.0);
        }
    }
}
