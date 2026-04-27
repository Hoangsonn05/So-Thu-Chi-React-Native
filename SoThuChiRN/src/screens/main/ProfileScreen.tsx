import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  Alert,
  Image,
  StyleSheet,
  StatusBar,
  Modal,
  TextInput,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import GlassBox from '../../components/GlassBox';
import { Colors, Spacing, BorderRadius, FontSize } from '../../theme/colors';
import db from '../../database/DatabaseHelper';
import { firebaseAuth, firestoreDb } from '../../config/firebase';
import { UserProfile } from '../../models/Transaction';

// ─── Sub-component: Detail Item ──────────────────────────────────────────────
const ProfileDetailItem = ({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: string;
}) => (
  <View style={styles.detailItem}>
    <View style={styles.iconContainer}>
      <Ionicons name={icon as any} size={20} color={Colors.accentBlue} />
    </View>
    <View style={styles.textContainer}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value || 'Chưa cập nhật'}</Text>
    </View>
  </View>
);

// ─── Sub-component: Modal Input Field ────────────────────────────────────────
const ModalInput = ({
  label,
  value,
  onChangeText,
  secureTextEntry = false,
  keyboardType = 'default',
  autoCapitalize = 'sentences',
}: {
  label: string;
  value: string;
  onChangeText: (t: string) => void;
  secureTextEntry?: boolean;
  keyboardType?: any;
  autoCapitalize?: any;
}) => {
  const [focused, setFocused] = useState(false);
  return (
    <View style={modalStyles.inputWrapper}>
      <Text style={[modalStyles.inputLabel, focused && modalStyles.inputLabelFocused]}>
        {label}
      </Text>
      <TextInput
        style={[modalStyles.textInput, focused && modalStyles.textInputFocused]}
        value={value}
        onChangeText={onChangeText}
        secureTextEntry={secureTextEntry}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize}
        autoCorrect={false}
        placeholderTextColor={Colors.placeholder}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      />
    </View>
  );
};

// ─── Main Screen ──────────────────────────────────────────────────────────────
export default function ProfileScreen({ navigation }: any) {
  const [user, setUser] = useState<UserProfile | null>(null);

  // Edit Profile Modal state
  const [editVisible, setEditVisible] = useState(false);
  const [editFullName, setEditFullName] = useState('');
  const [editUsername, setEditUsername] = useState('');
  const [editPhone, setEditPhone] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editLoading, setEditLoading] = useState(false);

  // Change Password Modal state
  const [pwdVisible, setPwdVisible] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [pwdLoading, setPwdLoading] = useState(false);

  useFocusEffect(
    React.useCallback(() => {
      loadUserData();
    }, [])
  );

  const loadUserData = async () => {
    try {
      // 1. Lấy dữ liệu local trước để hiển thị ngay (nhanh)
      const localData = await db.getLocalUser();
      if (localData) setUser(localData);

      // 2. Fetch dữ liệu "tươi" từ Firestore (nguồn sự thật)
      const uid = firebaseAuth().currentUser?.uid;
      if (uid) {
        const doc = await firestoreDb().collection('users').doc(uid).get();
        if (doc.exists()) {
          const cloudData = doc.data() as any;
          
          // Tạo object UserProfile chuẩn
          const updatedProfile: UserProfile = {
            fullName: cloudData.fullName || localData?.fullName || '',
            email: cloudData.email || localData?.email || '',
            phone: cloudData.phone || localData?.phone || '',
            username: cloudData.username || localData?.username || '',
            password: cloudData.password || localData?.password || '', // Giữ lại pass để login local
            photoURL: cloudData.photoURL || localData?.photoURL || null,
          };

          // 3. Cập nhật State và SQLite để đồng bộ cho lần sau
          setUser(updatedProfile);
          await db.updateUserLocal(updatedProfile);
        }
      }
    } catch (error) {
      console.error('Lỗi khi đồng bộ profile:', error);
    }
  };

  // ─── Open Edit Modal ────────────────────────────────────────────────────────
  const openEditModal = () => {
    setEditFullName(user?.fullName || '');
    setEditUsername(user?.username || '');
    setEditPhone(user?.phone || '');
    setEditEmail(user?.email || '');
    setEditVisible(true);
  };

  // ─── Save Profile Changes ───────────────────────────────────────────────────
  const handleSaveProfile = async () => {
    const uid = firebaseAuth().currentUser?.uid;
    if (!uid) {
      Alert.alert('Lỗi', 'Không tìm thấy phiên đăng nhập. Vui lòng đăng nhập lại.');
      return;
    }

    setEditLoading(true);
    try {
      // Build object chỉ chứa các field đã thay đổi
      const changedFirestore: Record<string, string> = {};
      const changedLocal: Record<string, string> = {};

      if (editFullName.trim() !== (user?.fullName || '')) {
        changedFirestore.fullName = editFullName.trim();
        changedLocal.fullName = editFullName.trim();
      }
      if (editUsername.trim() !== (user?.username || '')) {
        changedFirestore.username = editUsername.trim();
        changedLocal.username = editUsername.trim();
      }
      if (editPhone.trim() !== (user?.phone || '')) {
        changedFirestore.phone = editPhone.trim();
        changedLocal.phone = editPhone.trim();
      }
      if (editEmail.trim() !== (user?.email || '')) {
        changedFirestore.email = editEmail.trim();
        changedLocal.email = editEmail.trim();
      }

      if (Object.keys(changedFirestore).length === 0) {
        Alert.alert('Thông báo', 'Không có thông tin nào thay đổi.');
        setEditLoading(false);
        return;
      }

      // Cập nhật Firestore (chỉ các field thay đổi)
      await firestoreDb().collection('users').doc(uid).update(changedFirestore);

      // Cập nhật SQLite local (partial update)
      await db.updateUserLocal(changedLocal);

      // Cập nhật State tức thì (Optimistic UI Update)
      setUser(prev => prev ? ({ ...prev, ...changedLocal }) : null);

      setEditVisible(false);
      Alert.alert('Thành công', 'Thông tin cá nhân đã được cập nhật!');
    } catch (error: any) {
      Alert.alert('Lỗi', error.message || 'Không thể cập nhật thông tin. Vui lòng thử lại.');
    } finally {
      setEditLoading(false);
    }
  };

  // ─── Open Change Password Modal ─────────────────────────────────────────────
  const openPasswordModal = () => {
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setPwdVisible(true);
  };

  // ─── Save New Password ──────────────────────────────────────────────────────
  const handleSavePassword = async () => {
    // Validate
    if (!currentPassword.trim() || !newPassword.trim() || !confirmPassword.trim()) {
      Alert.alert('Thông báo', 'Vui lòng nhập đầy đủ tất cả các trường mật khẩu.');
      return;
    }
    if (newPassword !== confirmPassword) {
      Alert.alert('Lỗi', 'Mật khẩu mới và xác nhận mật khẩu không khớp.');
      return;
    }
    if (newPassword.length < 6) {
      Alert.alert('Lỗi', 'Mật khẩu mới phải có ít nhất 6 ký tự.');
      return;
    }
    if (newPassword === currentPassword) {
      Alert.alert('Thông báo', 'Mật khẩu mới phải khác mật khẩu hiện tại.');
      return;
    }

    const currentUser = firebaseAuth().currentUser;
    if (!currentUser || !currentUser.email) {
      Alert.alert('Lỗi', 'Không tìm thấy phiên đăng nhập. Vui lòng đăng nhập lại.');
      return;
    }

    setPwdLoading(true);
    try {
      // Bước 1: Reauthenticate với mật khẩu hiện tại
      const { EmailAuthProvider } = require('@react-native-firebase/auth');
      const credential = EmailAuthProvider.credential(
        currentUser.email,
        currentPassword.trim()
      );
      await currentUser.reauthenticateWithCredential(credential);

      // Bước 2: Đổi mật khẩu qua Firebase Auth
      await currentUser.updatePassword(newPassword.trim());

      const uid = currentUser.uid;

      // Bước 3: Cập nhật Firestore field password (đồng bộ với logic cũ)
      await firestoreDb()
        .collection('users')
        .doc(uid)
        .update({ password: newPassword.trim() });

      // Bước 4: Cập nhật SQLite local
      await db.updateUserLocal({ password: newPassword.trim() });

      setPwdVisible(false);
      Alert.alert('Thành công', 'Mật khẩu đã được thay đổi thành công!');
    } catch (error: any) {
      // Firebase Auth error codes
      if (
        error.code === 'auth/wrong-password' ||
        error.code === 'auth/invalid-credential'
      ) {
        Alert.alert('Lỗi', 'Mật khẩu hiện tại không chính xác.');
      } else if (error.code === 'auth/requires-recent-login') {
        Alert.alert(
          'Lỗi',
          'Phiên đăng nhập đã cũ. Vui lòng đăng xuất và đăng nhập lại trước khi đổi mật khẩu.'
        );
      } else {
        Alert.alert('Lỗi', error.message || 'Không thể đổi mật khẩu. Vui lòng thử lại.');
      }
    } finally {
      setPwdLoading(false);
    }
  };

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" />

      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity
          onPress={() => navigation.goBack()}
          style={styles.backButton}
          activeOpacity={0.7}
        >
          <Ionicons name="chevron-back" size={24} color="#FFF" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Hồ sơ cá nhân</Text>
        {/* Edit Icon */}
        <TouchableOpacity
          onPress={openEditModal}
          style={styles.editButton}
          activeOpacity={0.7}
        >
          <Ionicons name="create-outline" size={22} color={Colors.accentBlue} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Avatar Section */}
        <View style={styles.avatarSection}>
          <View style={styles.avatarGlow}>
            <View style={styles.avatarContainer}>
              {user?.photoURL ? (
                <Image source={{ uri: user.photoURL }} style={styles.avatar} />
              ) : (
                <View style={styles.placeholderAvatar}>
                  <Ionicons name="person" size={50} color="rgba(255,255,255,0.4)" />
                </View>
              )}
            </View>
          </View>
          <Text style={styles.userNameText}>{user?.fullName || 'Người dùng'}</Text>
          <Text style={styles.userEmailText}>{user?.email || 'Chưa liên kết email'}</Text>
        </View>

        <Text style={styles.sectionTitle}>THÔNG TIN TÀI KHOẢN</Text>
        <GlassBox padding={16} intensity={25} className="mb-6">
          <ProfileDetailItem
            label="Họ và tên"
            value={user?.fullName || ''}
            icon="person-outline"
          />
          <View style={styles.divider} />
          <ProfileDetailItem
            label="User Name"
            value={user?.username || ''}
            icon="at-outline"
          />
          <View style={styles.divider} />
          <ProfileDetailItem
            label="Số điện thoại"
            value={user?.phone || ''}
            icon="call-outline"
          />
          <View style={styles.divider} />
          <ProfileDetailItem
            label="Email"
            value={user?.email || ''}
            icon="mail-outline"
          />
        </GlassBox>

        <Text style={styles.sectionTitle}>BẢO MẬT</Text>
        <TouchableOpacity onPress={openPasswordModal} activeOpacity={0.8}>
          <GlassBox padding={16} intensity={20}>
            <View style={styles.passwordRow}>
              <View style={styles.passwordLeft}>
                <View style={styles.lockIconContainer}>
                  <Ionicons name="lock-closed" size={18} color="#FFD54F" />
                </View>
                <Text style={styles.passwordText}>Đổi mật khẩu</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color="rgba(255,255,255,0.3)" />
            </View>
          </GlassBox>
        </TouchableOpacity>

        <View style={styles.footerInfo}>
          <Text style={styles.footerText}>
            ID người dùng: {firebaseAuth().currentUser?.uid?.substring(0, 8)}...
          </Text>
        </View>
      </ScrollView>

      {/* ─── Modal: Chỉnh sửa thông tin ─────────────────────────────────────── */}
      <Modal
        visible={editVisible}
        transparent
        animationType="slide"
        onRequestClose={() => setEditVisible(false)}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={modalStyles.overlay}
        >
          <View style={modalStyles.sheet}>
            {/* Modal Header */}
            <View style={modalStyles.sheetHeader}>
              <Text style={modalStyles.sheetTitle}>Chỉnh sửa thông tin</Text>
              <TouchableOpacity
                onPress={() => setEditVisible(false)}
                style={modalStyles.closeBtn}
                activeOpacity={0.7}
              >
                <Ionicons name="close" size={22} color="rgba(255,255,255,0.6)" />
              </TouchableOpacity>
            </View>

            <ScrollView
              showsVerticalScrollIndicator={false}
              keyboardShouldPersistTaps="handled"
              contentContainerStyle={{ paddingBottom: 8 }}
            >
              <ModalInput
                label="Họ và tên"
                value={editFullName}
                onChangeText={setEditFullName}
                autoCapitalize="words"
              />
              <ModalInput
                label="Username"
                value={editUsername}
                onChangeText={setEditUsername}
                autoCapitalize="none"
              />
              <ModalInput
                label="Số điện thoại"
                value={editPhone}
                onChangeText={setEditPhone}
                keyboardType="phone-pad"
              />
              <ModalInput
                label="Email"
                value={editEmail}
                onChangeText={setEditEmail}
                keyboardType="email-address"
                autoCapitalize="none"
              />
            </ScrollView>

            {/* Buttons */}
            <View style={modalStyles.buttonRow}>
              <TouchableOpacity
                style={modalStyles.cancelBtn}
                onPress={() => setEditVisible(false)}
                activeOpacity={0.7}
              >
                <Text style={modalStyles.cancelBtnText}>Hủy</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[modalStyles.saveBtn, editLoading && modalStyles.btnDisabled]}
                onPress={handleSaveProfile}
                disabled={editLoading}
                activeOpacity={0.8}
              >
                {editLoading ? (
                  <ActivityIndicator color="#FFF" size="small" />
                ) : (
                  <Text style={modalStyles.saveBtnText}>Lưu</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* ─── Modal: Đổi mật khẩu ─────────────────────────────────────────────── */}
      <Modal
        visible={pwdVisible}
        transparent
        animationType="slide"
        onRequestClose={() => setPwdVisible(false)}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={modalStyles.overlay}
        >
          <View style={modalStyles.sheet}>
            {/* Modal Header */}
            <View style={modalStyles.sheetHeader}>
              <Text style={modalStyles.sheetTitle}>Đổi mật khẩu</Text>
              <TouchableOpacity
                onPress={() => setPwdVisible(false)}
                style={modalStyles.closeBtn}
                activeOpacity={0.7}
              >
                <Ionicons name="close" size={22} color="rgba(255,255,255,0.6)" />
              </TouchableOpacity>
            </View>

            <View style={modalStyles.securityNote}>
              <Ionicons name="shield-checkmark-outline" size={14} color={Colors.accentBlue} />
              <Text style={modalStyles.securityNoteText}>
                Mật khẩu được bảo mật qua Firebase Authentication
              </Text>
            </View>

            <ModalInput
              label="Mật khẩu hiện tại"
              value={currentPassword}
              onChangeText={setCurrentPassword}
              secureTextEntry
            />
            <ModalInput
              label="Mật khẩu mới (tối thiểu 6 ký tự)"
              value={newPassword}
              onChangeText={setNewPassword}
              secureTextEntry
            />
            <ModalInput
              label="Xác nhận mật khẩu mới"
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              secureTextEntry
            />

            {/* Buttons */}
            <View style={[modalStyles.buttonRow, { marginTop: Spacing.xl }]}>
              <TouchableOpacity
                style={modalStyles.cancelBtn}
                onPress={() => setPwdVisible(false)}
                activeOpacity={0.7}
              >
                <Text style={modalStyles.cancelBtnText}>Hủy</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[modalStyles.saveBtn, pwdLoading && modalStyles.btnDisabled]}
                onPress={handleSavePassword}
                disabled={pwdLoading}
                activeOpacity={0.8}
              >
                {pwdLoading ? (
                  <ActivityIndicator color="#FFF" size="small" />
                ) : (
                  <Text style={modalStyles.saveBtnText}>Xác nhận</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.bg,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 50,
    paddingHorizontal: 20,
    paddingBottom: 15,
  },
  backButton: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.08)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.1)',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#FFF',
    letterSpacing: 0.5,
  },
  editButton: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: 'rgba(0, 176, 255, 0.10)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 0.5,
    borderColor: 'rgba(0, 176, 255, 0.25)',
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingBottom: 50,
  },
  avatarSection: {
    alignItems: 'center',
    marginTop: 20,
    marginBottom: 35,
  },
  avatarGlow: {
    padding: 3,
    borderRadius: 65,
    backgroundColor: 'rgba(0, 176, 255, 0.15)',
    shadowColor: Colors.accentBlue,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.3,
    shadowRadius: 15,
    elevation: 10,
  },
  avatarContainer: {
    width: 110,
    height: 110,
    borderRadius: 55,
    backgroundColor: '#1A1A1A',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.15)',
    overflow: 'hidden',
  },
  avatar: {
    width: '100%',
    height: '100%',
  },
  placeholderAvatar: {
    width: '100%',
    height: '100%',
    backgroundColor: 'rgba(255,255,255,0.03)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  userNameText: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#FFF',
    marginTop: 15,
    letterSpacing: 0.5,
  },
  userEmailText: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.4)',
    marginTop: 4,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: 'bold',
    color: 'rgba(255,255,255,0.3)',
    marginBottom: 10,
    marginLeft: 4,
    letterSpacing: 1.2,
  },
  detailItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
  },
  iconContainer: {
    width: 38,
    height: 38,
    borderRadius: 12,
    backgroundColor: 'rgba(0, 176, 255, 0.08)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  textContainer: {
    flex: 1,
  },
  label: {
    fontSize: 11,
    color: 'rgba(255,255,255,0.3)',
    marginBottom: 2,
    textTransform: 'uppercase',
  },
  value: {
    fontSize: 15,
    color: '#FFF',
    fontWeight: '600',
  },
  divider: {
    height: 0.5,
    backgroundColor: 'rgba(255,255,255,0.05)',
    marginLeft: 54,
  },
  passwordRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  passwordLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 15,
  },
  lockIconContainer: {
    width: 38,
    height: 38,
    borderRadius: 12,
    backgroundColor: 'rgba(255, 213, 79, 0.08)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  passwordText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
  },
  footerInfo: {
    alignItems: 'center',
    marginTop: 30,
  },
  footerText: {
    fontSize: 12,
    color: 'rgba(255,255,255,0.2)',
  },
});

// ─── Modal Styles ─────────────────────────────────────────────────────────────
const modalStyles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.65)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: '#141414',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: 36,
    borderTopWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.1)',
    // Subtle glow on top border
    shadowColor: Colors.accentBlue,
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 20,
  },
  sheetHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.xl,
  },
  sheetTitle: {
    fontSize: FontSize.xxl,
    fontWeight: '700',
    color: '#FFF',
    letterSpacing: 0.3,
  },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.06)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  securityNote: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(0,176,255,0.08)',
    borderRadius: BorderRadius.sm,
    paddingHorizontal: 12,
    paddingVertical: 8,
    marginBottom: Spacing.xl,
    borderWidth: 0.5,
    borderColor: 'rgba(0,176,255,0.2)',
  },
  securityNoteText: {
    fontSize: FontSize.sm,
    color: Colors.accentBlue,
    flex: 1,
  },
  inputWrapper: {
    marginBottom: Spacing.lg,
  },
  inputLabel: {
    fontSize: FontSize.sm,
    color: 'rgba(255,255,255,0.4)',
    marginBottom: 6,
    fontWeight: '500',
  },
  inputLabelFocused: {
    color: Colors.accentBlue,
  },
  textInput: {
    height: 48,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
    borderRadius: BorderRadius.sm,
    paddingHorizontal: Spacing.lg,
    fontSize: FontSize.lg,
    color: '#FFF',
    backgroundColor: 'rgba(255,255,255,0.04)',
  },
  textInputFocused: {
    borderColor: Colors.accentBlue,
    borderWidth: 1.5,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: Spacing.xxl,
  },
  cancelBtn: {
    flex: 1,
    height: 52,
    borderRadius: BorderRadius.pill,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.15)',
  },
  cancelBtnText: {
    color: 'rgba(255,255,255,0.6)',
    fontSize: FontSize.xl,
    fontWeight: '600',
  },
  saveBtn: {
    flex: 1.6,
    height: 52,
    borderRadius: BorderRadius.pill,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.accentBlue,
    shadowColor: Colors.accentBlue,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 10,
    elevation: 6,
  },
  saveBtnText: {
    color: '#FFF',
    fontSize: FontSize.xl,
    fontWeight: '700',
  },
  btnDisabled: {
    opacity: 0.6,
  },
});
