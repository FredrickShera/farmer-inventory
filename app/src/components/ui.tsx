import React, { useState } from 'react';
import {
  ActivityIndicator, FlatList, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, Text,
  TextInput, TextInputProps, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, MIN_TOUCH, space } from '../theme';

export function Screen({ children }: { children: React.ReactNode }) {
  // KeyboardAvoidingView + ScrollView(keyboardShouldPersistTaps) keeps fields reachable with the keyboard open.
  return (
    <SafeAreaView style={styles.flex} edges={['top', 'left', 'right']}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.screen} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
          {children}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

export function Button({ title, onPress, disabled, loading, variant = 'primary' }: {
  title: string; onPress: () => void; disabled?: boolean; loading?: boolean; variant?: 'primary' | 'secondary' | 'danger';
}) {
  const off = disabled || loading;
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={title} accessibilityState={{ disabled: !!off, busy: !!loading }}
      disabled={off} onPress={onPress}
      style={({ pressed }) => [styles.btn, styles[variant], off && styles.btnOff, pressed && { opacity: 0.85 }]}>
      {loading ? <ActivityIndicator color={variant === 'secondary' ? colors.primary : '#fff'} /> :
        <Text style={[styles.btnText, variant === 'secondary' && { color: colors.primary }]}>{title}</Text>}
    </Pressable>
  );
}

export function TextField({ label, error, ...props }: TextInputProps & { label: string; error?: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput accessibilityLabel={label} placeholderTextColor={colors.muted} autoCapitalize="none" autoCorrect={false}
        style={[styles.input, !!error && { borderColor: colors.danger }, props.editable === false && styles.inputOff]} {...props} />
      {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
    </View>
  );
}

export interface Option<V extends string | number> { value: V; label: string }

/** Dropdown: a tappable field that opens a modal list (works the same on iOS and Android). */
export function SelectField<V extends string | number>({ label, value, options, onChange, error, disabled, placeholder = 'Select…' }: {
  label: string; value: V | null; options: Option<V>[]; onChange: (v: V) => void; error?: string; disabled?: boolean; placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.value === value);
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled: !!disabled }}
        disabled={disabled} onPress={() => setOpen(true)} style={[styles.input, styles.select, !!error && { borderColor: colors.danger }, disabled && styles.inputOff]}>
        <Text style={{ color: current ? colors.text : colors.muted, fontSize: 16 }}>{current?.label ?? placeholder}</Text>
        <Text style={{ color: colors.muted }}>▾</Text>
      </Pressable>
      {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)} />
        <View style={styles.sheet}>
          <Text style={styles.sheetTitle}>{label}</Text>
          <FlatList data={options} keyExtractor={(o) => String(o.value)} ListEmptyComponent={<Text style={styles.muted}>No options</Text>}
            renderItem={({ item }) => (
              <Pressable accessibilityRole="button" accessibilityLabel={item.label} style={styles.option}
                onPress={() => { onChange(item.value); setOpen(false); }}>
                <Text style={[styles.optionText, item.value === value && { color: colors.primary, fontWeight: '700' }]}>{item.label}</Text>
              </Pressable>
            )} />
          <Button title="Cancel" variant="secondary" onPress={() => setOpen(false)} />
        </View>
      </Modal>
    </View>
  );
}

export function Segmented<V extends string>({ label, value, options, onChange, disabled }: {
  label: string; value: V; options: V[]; onChange: (v: V) => void; disabled?: boolean;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.segRow}>
        {options.map((o) => (
          <Pressable key={o} accessibilityRole="button" accessibilityLabel={`${label} ${o}`} accessibilityState={{ selected: o === value, disabled: !!disabled }}
            disabled={disabled} onPress={() => onChange(o)} style={[styles.seg, o === value && styles.segOn]}>
            <Text style={[styles.segText, o === value && { color: '#fff' }]}>{o}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

export const Loading = ({ text = 'Loading…' }: { text?: string }) => (
  <View style={styles.center} accessibilityLiveRegion="polite"><ActivityIndicator size="large" color={colors.primary} /><Text style={styles.muted}>{text}</Text></View>
);
export const ErrorState = ({ message, onRetry }: { message: string; onRetry: () => void }) => (
  <View style={styles.center}><Text accessibilityRole="alert" style={[styles.error, { fontSize: 16, textAlign: 'center' }]}>{message}</Text><Button title="Try again" onPress={onRetry} /></View>
);
export const EmptyState = ({ title, hint }: { title: string; hint?: string }) => (
  <View style={styles.center}><Text style={styles.sheetTitle}>{title}</Text>{hint ? <Text style={styles.muted}>{hint}</Text> : null}</View>
);
export const Banner = ({ text }: { text: string }) => (<View style={styles.banner}><Text accessibilityRole="alert" style={{ color: colors.danger }}>{text}</Text></View>);

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.bg },
  screen: { padding: space.lg, gap: space.sm, paddingBottom: space.xl * 2 },
  btn: { minHeight: MIN_TOUCH, borderRadius: 10, alignItems: 'center', justifyContent: 'center', paddingHorizontal: space.lg, marginTop: space.sm },
  primary: { backgroundColor: colors.primary }, secondary: { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.primary },
  danger: { backgroundColor: colors.danger }, btnOff: { opacity: 0.5 }, btnText: { color: colors.primaryText, fontSize: 16, fontWeight: '600' },
  field: { marginBottom: space.sm }, label: { fontSize: 14, fontWeight: '600', color: colors.text, marginBottom: space.xs },
  input: { minHeight: MIN_TOUCH, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: space.md, fontSize: 16, color: colors.text, backgroundColor: colors.card },
  inputOff: { backgroundColor: '#EEF0EE', color: colors.muted },
  select: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  error: { color: colors.danger, fontSize: 13, marginTop: space.xs }, muted: { color: colors.muted, textAlign: 'center' },
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.35)' },
  sheet: { backgroundColor: colors.card, padding: space.lg, maxHeight: '70%', borderTopLeftRadius: 16, borderTopRightRadius: 16 },
  sheetTitle: { fontSize: 18, fontWeight: '700', color: colors.text, marginBottom: space.sm },
  option: { minHeight: MIN_TOUCH, justifyContent: 'center', borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  optionText: { fontSize: 16, color: colors.text },
  segRow: { flexDirection: 'row', gap: space.sm },
  seg: { flex: 1, minHeight: MIN_TOUCH, borderRadius: 10, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card },
  segOn: { backgroundColor: colors.primary, borderColor: colors.primary }, segText: { fontSize: 16, fontWeight: '600', color: colors.text },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl, gap: space.md },
  banner: { backgroundColor: '#FDECEA', padding: space.md, borderRadius: 10, marginBottom: space.sm },
});
