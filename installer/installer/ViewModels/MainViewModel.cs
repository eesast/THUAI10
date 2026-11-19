using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Windows.Input;
using Avalonia.Threading;
using Thuai10.Launcher.Services;

namespace Thuai10.Launcher.ViewModels;

public sealed class MainViewModel : INotifyPropertyChanged, IDisposable
{
    private readonly PackageService packages = new();
    private readonly DocumentService documents = new();
    private readonly LaunchService launcher = new();
    private CancellationTokenSource? downloadCancellation;
    private PackageCheck? lastCheck;
    private bool busy;
    private string catalogAddress = string.Empty;
    private string installRoot = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "THUAI10");
    private string status = "填写文件清单地址，选择安装位置，然后检查更新。";
    private string version = "尚未检查";
    private string documentText = "下载选手包后，可在这里阅读 docs 文件夹里的 Markdown 文档。";
    private string? documentAssetPath;
    private string? selectedDocument;
    private string searchText = string.Empty;
    private string searchStatus = string.Empty;
    private double progressPercent;
    private string progressText = string.Empty;
    private string launchLog = string.Empty;

    public event PropertyChangedEventHandler? PropertyChanged;

    public MainViewModel()
    {
        launcher.Log += message => Dispatcher.UIThread.Post(() => AppendLog(message));
        CheckCommand = new RelayCommand(async () => await CheckAsync());
        DownloadCommand = new RelayCommand(async () => await DownloadAsync());
        PauseCommand = new RelayCommand(Pause);
        RefreshDocsCommand = new RelayCommand(RefreshDocuments);
        LaunchCommand = new RelayCommand(async () => await LaunchAsync());
        StopCommand = new RelayCommand(Stop);
        LoadSettings();
        RefreshDocuments();
    }

    public string CatalogAddress
    {
        get => catalogAddress;
        set { catalogAddress = value; Changed(); }
    }

    public string InstallRoot
    {
        get => installRoot;
        set
        {
            installRoot = value;
            lastCheck = null;
            Changed();
            RefreshDocuments();
        }
    }

    public string Status
    {
        get => status;
        private set { status = value; Changed(); }
    }

    public string Version
    {
        get => version;
        private set { version = value; Changed(); }
    }

    public double ProgressPercent
    {
        get => progressPercent;
        private set { progressPercent = value; Changed(); }
    }

    public string ProgressText
    {
        get => progressText;
        private set { progressText = value; Changed(); }
    }

    public ObservableCollection<string> DocumentNames { get; } = new();

    public string? SelectedDocument
    {
        get => selectedDocument;
        set
        {
            selectedDocument = value;
            Changed();
            _ = ReadDocumentAsync(value);
        }
    }

    public string DocumentText
    {
        get => documentText;
        private set { documentText = value; Changed(); UpdateSearch(); }
    }

    public string? DocumentAssetPath
    {
        get => documentAssetPath;
        private set { documentAssetPath = value; Changed(); }
    }

    public string SearchText
    {
        get => searchText;
        set { searchText = value; Changed(); UpdateSearch(); }
    }

    public string SearchStatus
    {
        get => searchStatus;
        private set { searchStatus = value; Changed(); }
    }

    public string LaunchLog
    {
        get => launchLog;
        private set { launchLog = value; Changed(); }
    }

    public ICommand CheckCommand { get; }
    public ICommand DownloadCommand { get; }
    public ICommand PauseCommand { get; }
    public ICommand RefreshDocsCommand { get; }
    public ICommand LaunchCommand { get; }
    public ICommand StopCommand { get; }

    private async Task CheckAsync()
    {
        if (busy) return;
        busy = true;
        try
        {
            SaveSettings();
            Status = "正在读取云端清单并校验本地文件…";
            lastCheck = await packages.CheckAsync(CatalogAddress.Trim(), InstallRoot.Trim(), CancellationToken.None);
            Version = lastCheck.Catalog.Version;
            int protectedCount = lastCheck.Changes.Count(c => c.IsModifiedByUser);
            int downloadable = lastCheck.Changes.Count - protectedCount;
            Status = downloadable == 0 && protectedCount == 0
                ? "已是最新版本。"
                : $"待下载 {downloadable} 个文件；保留本地修改 {protectedCount} 个文件。";
        }
        catch (Exception error)
        {
            lastCheck = null;
            Status = $"检查失败：{error.Message}";
        }
        finally
        {
            busy = false;
        }
    }

    private async Task DownloadAsync()
    {
        if (busy) return;
        if (lastCheck is null)
        {
            Status = "请先检查更新。";
            return;
        }

        busy = true;
        downloadCancellation = new CancellationTokenSource();
        try
        {
            Status = "正在下载…";
            IProgress<(string File, long Received, long Total)> progress =
                new Progress<(string File, long Received, long Total)>(p =>
                {
                    ProgressPercent = p.Total > 0 ? 100.0 * p.Received / p.Total : 0;
                    ProgressText = $"{p.File} · {p.Received:N0} / {p.Total:N0} 字节";
                });
            await packages.InstallAsync(lastCheck, InstallRoot.Trim(), progress, downloadCancellation.Token);
            int protectedCount = lastCheck.Changes.Count(c => c.IsModifiedByUser);
            Status = protectedCount == 0
                ? "同步完成。"
                : $"同步完成；保留 {protectedCount} 个本地修改文件。";
            RefreshDocuments();
            lastCheck = null;
        }
        catch (OperationCanceledException)
        {
            Status = "已暂停；再次检查更新后可从未完成文件的断点继续。";
        }
        catch (Exception error)
        {
            Status = $"下载失败：{error.Message}";
        }
        finally
        {
            downloadCancellation.Dispose();
            downloadCancellation = null;
            busy = false;
        }
    }

    private void Pause() => downloadCancellation?.Cancel();

    private void RefreshDocuments()
    {
        DocumentNames.Clear();
        foreach (string name in documents.List(InstallRoot.Trim()))
        {
            DocumentNames.Add(name);
        }

        if (DocumentNames.Count == 0)
        {
            SelectedDocument = null;
            DocumentText = "当前安装目录尚无 docs/*.md 文档。";
        }
        else if (selectedDocument is null || !DocumentNames.Contains(selectedDocument))
        {
            SelectedDocument = DocumentNames[0];
        }
    }

    private async Task ReadDocumentAsync(string? name)
    {
        if (name is null) return;
        try
        {
            string content = await documents.ReadAsync(InstallRoot.Trim(), name, CancellationToken.None);
            if (selectedDocument == name)
            {
                DocumentAssetPath = Path.GetFullPath(Path.Combine(InstallRoot.Trim(), "docs", name));
                DocumentText = content;
            }
        }
        catch (Exception error)
        {
            DocumentText = $"文档读取失败：{error.Message}";
        }
    }

    private void UpdateSearch()
    {
        if (string.IsNullOrWhiteSpace(SearchText))
        {
            SearchStatus = "";
            return;
        }

        int count = 0;
        int position = 0;
        while ((position = DocumentText.IndexOf(SearchText, position, StringComparison.OrdinalIgnoreCase)) >= 0)
        {
            count++;
            position += SearchText.Length;
        }

        SearchStatus = $"当前文档找到 {count} 处";
    }

    private async Task LaunchAsync()
    {
        try
        {
            AppendLog("正在检查启动配置…");
            await launcher.StartAsync(InstallRoot.Trim(), CancellationToken.None);
        }
        catch (Exception error)
        {
            AppendLog($"启动失败：{error.Message}");
        }
    }

    private void Stop() => launcher.Stop();

    private void AppendLog(string message)
    {
        LaunchLog += $"[{DateTime.Now:HH:mm:ss}] {message}{Environment.NewLine}";
        if (LaunchLog.Length > 20000) LaunchLog = LaunchLog[^15000..];
    }

    private static string SettingsPath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "THUAI10", "launcher-settings.json");

    private void LoadSettings()
    {
        try
        {
            if (!File.Exists(SettingsPath)) return;
            LauncherSettings? settings = JsonSerializer.Deserialize<LauncherSettings>(File.ReadAllText(SettingsPath));
            if (settings is null) return;
            catalogAddress = settings.CatalogAddress ?? string.Empty;
            installRoot = settings.InstallRoot ?? installRoot;
        }
        catch (Exception) { }
    }

    private void SaveSettings()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
        File.WriteAllText(SettingsPath, JsonSerializer.Serialize(
            new LauncherSettings { CatalogAddress = CatalogAddress, InstallRoot = InstallRoot }));
    }

    private void Changed([CallerMemberName] string? name = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }

    public void Dispose()
    {
        downloadCancellation?.Cancel();
        launcher.Dispose();
    }

    private sealed class LauncherSettings
    {
        public string? CatalogAddress { get; set; }
        public string? InstallRoot { get; set; }
    }
}

internal sealed class RelayCommand(Action action) : ICommand
{
    public event EventHandler? CanExecuteChanged { add { } remove { } }
    public bool CanExecute(object? parameter) => true;
    public void Execute(object? parameter) => action();
}
