/**
 * ExportService.ts
 * Logic for generating PDF and Excel documents and opening the Share Sheet.
 */

import { Platform, Alert } from 'react-native';
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';
import * as FileSystem from 'expo-file-system';
import XLSX from 'xlsx';
import { Transaction } from '../models/Transaction';
import { API_ENDPOINTS } from '../config/api';

const DIRECTORY_URI_FILE = `${FileSystem.documentDirectory}save_directory_uri.txt`;

class ExportService {
  /**
   * Export a list of transactions to a PDF file and share it (iOS) or save it (Android).
   */
  async exportToPDF(transactions: Transaction[], title: string = 'Báo cáo giao dịch'): Promise<void> {
    try {
      const html = this.generateHTML(transactions, title);
      const { uri } = await Print.printToFileAsync({ html });
      const safeTitle = title.replace(/\s+/g, '_');
      const pdfUri = `${FileSystem.cacheDirectory}${safeTitle}_${Date.now()}.pdf`;
      await FileSystem.moveAsync({ from: uri, to: pdfUri });

      if (Platform.OS === 'android') {
        await this.saveToAndroidDevice(pdfUri, `${safeTitle}.pdf`);
      } else {
        if (await Sharing.isAvailableAsync()) {
          await Sharing.shareAsync(pdfUri);
        } else {
          Alert.alert('Lỗi', 'Tính năng chia sẻ không khả dụng trên thiết bị này');
        }
      }
    } catch (error) {
      console.error('Export PDF Error:', error);
      throw error;
    }
  }

  /**
   * Internal helper to save file to Android public storage using SAF.
   */
  private async saveToAndroidDevice(fileUri: string, fileName: string): Promise<void> {
    try {
      let directoryUri: string | null = null;

      // Try to read existing directory URI
      const info = await FileSystem.getInfoAsync(DIRECTORY_URI_FILE);
      if (info.exists) {
        directoryUri = await FileSystem.readAsStringAsync(DIRECTORY_URI_FILE);
      }

      // If no directory URI or it's invalid, request permission
      if (!directoryUri) {
        const permissions = await FileSystem.StorageAccessFramework.requestDirectoryPermissionsAsync();
        if (permissions.granted) {
          directoryUri = permissions.directoryUri;
          await FileSystem.writeAsStringAsync(DIRECTORY_URI_FILE, directoryUri);
        } else {
          // User cancelled, fallback to sharing
          if (await Sharing.isAvailableAsync()) {
            await Sharing.shareAsync(fileUri);
          }
          return;
        }
      }

      // Create the file in the selected directory
      const base64 = await FileSystem.readAsStringAsync(fileUri, { encoding: FileSystem.EncodingType.Base64 });
      const newFileUri = await FileSystem.StorageAccessFramework.createFileAsync(
        directoryUri,
        fileName,
        'application/pdf'
      );

      await FileSystem.writeAsStringAsync(newFileUri, base64, { encoding: FileSystem.EncodingType.Base64 });
      Alert.alert('Thành công', `Báo cáo đã được lưu vào máy.`);
    } catch (error) {
      console.error('Save to Android Error:', error);
      // Fallback to sharing if something goes wrong
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(fileUri);
      }
    }
  }

  /**
   * Export all transactions to an Excel sheet and share it.
   */
  async exportToExcel(transactions: Transaction[], fileName: string = 'So_Thu_Chi_Report.xlsx'): Promise<void> {
    try {
      // 1. Map transactions to simple objects for Excel
      const data = transactions.map((t) => ({
        'Ngày': t.date,
        'Hạng mục': t.category,
        'Ghi chú': t.note,
        'Loại': t.type === 1 ? 'Thu nhập' : 'Chi tiêu',
        'Số tiền (đ)': t.amount,
        'Người tạo': t.createdBy || '',
        'Thiết bị': t.deviceName || '',
      }));

      // 2. Create worksheet
      const ws = XLSX.utils.json_to_sheet(data);
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Giao dịch');

      // 3. Generate binary string
      const wbout = XLSX.write(wb, { type: 'base64', bookType: 'xlsx' });
      const uri = `${FileSystem.cacheDirectory}${fileName}`;

      // 4. Write file and share
      await FileSystem.writeAsStringAsync(uri, wbout, { encoding: FileSystem.EncodingType.Base64 });

      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(uri);
      } else {
        alert('Tính năng chia sẻ không khả dụng trên thiết bị này');
      }
    } catch (error) {
      console.error('Export Excel Error:', error);
      throw error;
    }
  }

  /**
   * Gửi yêu cầu báo cáo Excel qua Backend để gửi tới Mail người dùng.
   */
  async triggerEmailReport(userId: string, userEmail: string): Promise<{ success: boolean; message: string }> {
    try {
      const response = await fetch(API_ENDPOINTS.EXPORT_EMAIL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'ngrok-skip-browser-warning': '69420', // Bypass ngrok warning page
        },
        body: JSON.stringify({ userId, userEmail }),
      });

      const text = await response.text();
      let result;
      try {
        result = JSON.parse(text);
      } catch (e) {
        console.error('Non-JSON response:', text);
        return { success: false, message: `Lỗi định dạng phản hồi từ Server: ${text.substring(0, 100)}` };
      }

      if (response.ok && result.success) {
        return { success: true, message: result.message || 'Đã gửi báo cáo thành công!' };
      } else {
        return { success: false, message: result?.detail || result?.message || 'Lỗi từ phía Server.' };
      }
    } catch (error: any) {
      console.error('Trigger Email Report Error:', error);
      return { success: false, message: 'Không thể kết nối tới Server. Vui lòng kiểm tra Ngrok.' };
    }
  }

  /**
   * Internal helper to generate a clean, professional HTML template for the PDF.
   */
  private generateHTML(transactions: Transaction[], title: string): string {
    const rows = transactions.map((t) => `
      <tr>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;">${t.date}</td>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;">${t.category}</td>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;">${t.note}</td>
        <td style="padding: 8px; border-bottom: 1px solid #ddd; color: ${t.type === 1 ? '#00c853' : '#ff5252'}; text-align: right; font-weight: bold;">
          ${t.type === 1 ? '+' : '-'}${t.amount.toLocaleString()}đ
        </td>
      </tr>
    `).join('');

    const totalIncome = transactions.filter(t => t.type === 1).reduce((sum, t) => sum + t.amount, 0);
    const totalExpense = transactions.filter(t => t.type === 0).reduce((sum, t) => sum + t.amount, 0);

    return `
      <html>
        <head>
          <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0, user-scalable=no" />
          <style>
            body { font-family: 'Helvetica', 'Arial', sans-serif; color: #333; padding: 20px; }
            .header { text-align: center; margin-bottom: 30px; border-bottom: 2px solid #00b0ff; padding-bottom: 10px; }
            .summary { background: #f5f5f5; padding: 15px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; }
            table { width: 100%; border-collapse: collapse; }
            th { text-align: left; background-color: #f8f9fa; padding: 10px; border-bottom: 2px solid #ddd; }
            .footer { margin-top: 30px; font-size: 10px; color: #777; text-align: center; }
          </style>
        </head>
        <body>
          <div class="header">
            <h1>${title}</h1>
            <p>Ứng dụng Sổ Thu Chi - Báo cáo xuất ngày ${new Date().toLocaleDateString('vi-VN')}</p>
          </div>
          
          <div class="summary">
            <div><strong>Tổng thu:</strong> <span style="color: #00c853;">+${totalIncome.toLocaleString()}đ</span></div>
            <div><strong>Tổng chi:</strong> <span style="color: #ff5252;">-${totalExpense.toLocaleString()}đ</span></div>
            <div><strong>Số dư:</strong> <strong>${(totalIncome - totalExpense).toLocaleString()}đ</strong></div>
          </div>

          <table>
            <thead>
              <tr>
                <th>Ngày</th>
                <th>Hạng mục</th>
                <th>Ghi chú</th>
                <th style="text-align: right;">Số tiền</th>
              </tr>
            </thead>
            <tbody>
              ${rows}
            </tbody>
          </table>

          <div class="footer">
            <p>Báo cáo được tạo tự động bởi ứng dụng Sổ Thu Chi. Cảm ơn bạn đã tin dùng.</p>
          </div>
        </body>
      </html>
    `;
  }
}

export const exportService = new ExportService();
export default exportService;
