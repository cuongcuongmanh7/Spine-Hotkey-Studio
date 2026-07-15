using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Launcher
{
    [STAThread]
    private static void Main()
    {
        string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
        string appPath = Path.Combine(baseDirectory, "app.py");

        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = "pythonw.exe",
                Arguments = "\"" + appPath + "\"",
                WorkingDirectory = baseDirectory,
                UseShellExecute = false,
                CreateNoWindow = true
            });
        }
        catch (Exception exception)
        {
            MessageBox.Show(
                "Không thể mở Spine Hotkey Studio.\n\n" + exception.Message +
                "\n\nBạn vẫn có thể chạy file launch.bat.",
                "Spine Hotkey Studio",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
        }
    }
}

