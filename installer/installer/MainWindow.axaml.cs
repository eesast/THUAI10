using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using Thuai10.Launcher.ViewModels;

namespace Thuai10.Launcher;

public partial class MainWindow : Window
{
    private readonly MainViewModel model = new();

    public MainWindow()
    {
        InitializeComponent();
        DataContext = model;
        Closed += (_, _) => model.Dispose();
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
