package com.flowwwclient.mixin;

import com.flowwwclient.FlowwwClientConfig;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.render.entity.EntityRenderer;
import net.minecraft.client.util.math.MatrixStack;
import net.minecraft.entity.Entity;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.text.Style;
import net.minecraft.text.Text;
import net.minecraft.text.TextColor;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;
import org.spongepowered.asm.mixin.injection.invoke.arg.Args;
import org.spongepowered.asm.mixin.injection.ModifyArgs;

@Mixin(EntityRenderer.class)
public abstract class EntityRendererMixin<T extends Entity> {
    @ModifyVariable(method = "renderLabelIfPresent", at = @At("HEAD"), argsOnly = true, ordinal = 0)
    private Text flowwwclient$decoratePlayerName(Text original) {
        if (!FlowwwClientConfig.nametagEnabled || original == null || FlowwwClientConfig.nametagSymbol == null || FlowwwClientConfig.nametagSymbol.isBlank()) {
            return original;
        }
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.world == null) return original;
        String label = original.getString();
        boolean isPlayerLabel = client.world.getPlayers().stream().anyMatch(player ->
                label.equals(player.getDisplayName().getString()) || label.equals(player.getName().getString())
        );
        if (!isPlayerLabel) return original;

        Style markerStyle = Style.EMPTY.withColor(TextColor.fromRgb(FlowwwClientConfig.colorAsRgb())).withBold(true);
        return Text.literal(FlowwwClientConfig.nametagSymbol + " ").setStyle(markerStyle).append(original);
    }

    @ModifyArgs(method = "renderLabelIfPresent", at = @At(value = "INVOKE", target = "Lnet/minecraft/client/util/math/MatrixStack;scale(FFF)V"))
    private void flowwwclient$scaleNameLabels(Args args) {
        double size = FlowwwClientConfig.nametagScale;
        if (!FlowwwClientConfig.nametagEnabled || Math.abs(size - 1.0) < 0.001) return;
        args.set(0, ((Number) args.get(0)).floatValue() * (float) size);
        args.set(1, ((Number) args.get(1)).floatValue() * (float) size);
        args.set(2, ((Number) args.get(2)).floatValue() * (float) size);
    }
}
