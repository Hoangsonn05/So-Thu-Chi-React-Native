import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Modal,
  BackHandler,
  Dimensions,
} from 'react-native';
import { BlurView } from 'expo-blur';
import { WifiOff } from 'lucide-react-native';
import { Colors, Spacing, BorderRadius, FontSize } from '../theme/colors';

const { width, height } = Dimensions.get('window');

interface OfflineStatusModalProps {
  isVisible: boolean;
  onContinue: () => void;
}

const OfflineStatusModal: React.FC<OfflineStatusModalProps> = ({ isVisible, onContinue }) => {
  const handleExit = () => {
    BackHandler.exitApp();
  };

  return (
    <Modal
      transparent
      visible={isVisible}
      animationType="fade"
      statusBarTranslucent
    >
      <View style={styles.overlay}>
        <BlurView intensity={20} tint="dark" style={StyleSheet.absoluteFill} />
        
        <View style={styles.container}>
          <BlurView intensity={90} tint="dark" style={StyleSheet.absoluteFill} />
          <View style={styles.content}>
            <View style={styles.iconContainer}>
              <View style={styles.iconPulse}>
                <WifiOff size={40} color="rgba(239, 68, 68, 0.8)" />
              </View>
            </View>

            <Text style={styles.title}>Chế độ ngoại tuyến</Text>
            
            <Text style={styles.description}>
              Dữ liệu sẽ được bảo vệ tại bộ nhớ máy và tự động đồng bộ lên Cloud khi có mạng.
            </Text>

            <View style={styles.buttonRow}>
              <TouchableOpacity 
                style={styles.exitButton} 
                onPress={handleExit}
                activeOpacity={0.7}
              >
                <Text style={styles.exitButtonText}>Đóng app</Text>
              </TouchableOpacity>

              <TouchableOpacity 
                style={styles.continueButton} 
                onPress={onContinue}
                activeOpacity={0.8}
              >
                <Text style={styles.continueButtonText}>Tiếp tục</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)', // Backdrop
    justifyContent: 'center',
    alignItems: 'center',
    padding: Spacing.xl,
  },
  container: {
    width: width - 48,
    borderRadius: 24,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.3)',
    backgroundColor: '#121212',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.3,
    shadowRadius: 20,
    elevation: 10,
  },
  content: {
    padding: 24,
    alignItems: 'center',
  },
  iconContainer: {
    marginBottom: 20,
  },
  iconPulse: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.2)',
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    color: Colors.textPrimary,
    marginBottom: 12,
  },
  description: {
    fontSize: FontSize.md,
    color: Colors.spatialTextPrimary,
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 24,
    fontWeight: '600',
  },
  buttonRow: {
    flexDirection: 'row',
    width: '100%',
    gap: 12,
  },
  exitButton: {
    flex: 1,
    height: 48,
    borderRadius: BorderRadius.pill,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
  },
  exitButtonText: {
    color: Colors.textSecondary,
    fontSize: FontSize.md,
    fontWeight: '600',
  },
  continueButton: {
    flex: 1,
    height: 48,
    borderRadius: BorderRadius.pill,
    backgroundColor: Colors.primaryGreen,
    justifyContent: 'center',
    alignItems: 'center',
  },
  continueButtonText: {
    color: Colors.white,
    fontSize: FontSize.md,
    fontWeight: '700',
  },
});

export default OfflineStatusModal;
