using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using Avalonia.VisualTree;
using Thuai10.Launcher.ViewModels;

namespace Thuai10.Launcher;

public partial class MainWindow : Window
{
    private readonly MainViewModel model = new();

    public MainWindow()
    {
        InitializeComponent();
        DataContext = model;
        SetupWindowChrome();
        AddHandler(PointerPressedEvent, OnChromePointerPressed, RoutingStrategies.Tunnel, handledEventsToo: true);
        Closed += (_, _) => model.Dispose();
        KeyDown += (_, e) =>
        {
            if (e.Key == Key.W && e.KeyModifiers.HasFlag(KeyModifiers.Meta))
            {
                e.Handled = true;
                Close();
            }
        };
    }

    /// <summary>按平台决定是否把内容延伸到标题栏，并标记样式类名。</summary>
    private void SetupWindowChrome()
    {
        if (OperatingSystem.IsMacOS())
        {
            Classes.Add("mac");
            ExtendClientAreaToDecorationsHint = true;
            ExtendClientAreaChromeHints = Avalonia.Platform.ExtendClientAreaChromeHints.PreferSystemChrome;
            ExtendClientAreaTitleBarHeightHint = 52;
        }
        else if (OperatingSystem.IsWindows())
        {
            Classes.Add("win");
            ExtendClientAreaToDecorationsHint = true;
            ExtendClientAreaChromeHints = Avalonia.Platform.ExtendClientAreaChromeHints.PreferSystemChrome;
            ExtendClientAreaTitleBarHeightHint = 52;
        }
        else
        {
            Classes.Add("linux");
            ExtendClientAreaToDecorationsHint = false;
        }

        UpdateTransparencyClass();
        PropertyChanged += (_, e) =>
        {
            if (e.Property == ActualTransparencyLevelProperty) UpdateTransparencyClass();
        };
        Opened += (_, _) => UpdateTransparencyClass();
    }

    /// <summary>系统不支持窗口透明（或 Linux）时，侧栏改用不透明底色。</summary>
    private void UpdateTransparencyClass()
    {
        // Linux 不扩展客户区，始终使用不透明侧栏；其他平台在系统不支持透明时回退。
        bool noTransparency = !OperatingSystem.IsMacOS() && !OperatingSystem.IsWindows();
        Classes.Set("opaque", noTransparency || ActualTransparencyLevel == WindowTransparencyLevel.None);
    }

    /// <summary>标题栏区域拖动窗口，双击按系统习惯缩放。</summary>
    private void OnChromePointerPressed(object? sender, PointerPressedEventArgs e)
    {
        if (!e.GetCurrentPoint(this).Properties.IsLeftButtonPressed) return;
        if (e.Source is not Visual source) return;
        if (!IsInDragRegion(source) || HasInteractiveAncestor(source)) return;

        if (e.ClickCount == 2)
        {
            WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
            e.Handled = true;
            return;
        }

        BeginMoveDrag(e);
    }

    private bool IsInDragRegion(Visual source)
    {
        for (Visual? visual = source; visual is not null && visual != this; visual = visual.GetVisualParent())
        {
            if (visual is Control control && control.Classes.Contains("drag")) return true;
        }

        return false;
    }

    private bool HasInteractiveAncestor(Visual source)
    {
        for (Visual? visual = source; visual is not null && visual != this; visual = visual.GetVisualParent())
        {
            if (visual is Button or TextBox or ScrollBar or ListBoxItem or TabItem or ToggleButton) return true;
        }

        return false;
    }

    private async void ChooseFolderClick(object? sender, RoutedEventArgs e)
    {
        IReadOnlyList<Avalonia.Platform.Storage.IStorageFolder> folders =
            await StorageProvider.OpenFolderPickerAsync(new()
            {
                Title = "选择选手包安装目录",
                AllowMultiple = false
            });
        if (folders.Count > 0 && folders[0].TryGetLocalPath() is string path)
        {
            model.InstallRoot = path;
        }
    }
}
