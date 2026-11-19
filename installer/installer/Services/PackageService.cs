using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text.Json;

namespace Thuai10.Launcher.Services;

public sealed class PackageCatalog
{
    public string Version { get; set; } = string.Empty;
    public List<PackageFile> Files { get; set; } = new();
}

public sealed class PackageFile
{
    public string Path { get; set; } = string.Empty;
    public string Url { get; set; } = string.Empty;
    public long Size { get; set; }
    public string Sha256 { get; set; } = string.Empty;
}

public sealed record PackageChange(PackageFile File, bool IsModifiedByUser);

public sealed class PackageCheck
{
    public required PackageCatalog Catalog { get; init; }
    public required Uri CatalogUrl { get; init; }
    public required List<PackageChange> Changes { get; init; }
}

public sealed class PackageService
{
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNameCaseInsensitive = true,
        WriteIndented = true
    };

    private readonly HttpClient client = new() { Timeout = TimeSpan.FromMinutes(10) };

    public async Task<PackageCheck> CheckAsync(string catalogAddress, string installRoot, CancellationToken token)
    {
        if (!Uri.TryCreate(catalogAddress, UriKind.Absolute, out Uri? catalogUrl)
            || !IsAllowedUrl(catalogUrl))
        {
            throw new InvalidOperationException("请输入 HTTPS 清单地址；本机测试可使用 localhost HTTP。");
        }

        using HttpResponseMessage response = await client.GetAsync(catalogUrl, token);
        response.EnsureSuccessStatusCode();
        await using Stream stream = await response.Content.ReadAsStreamAsync(token);
        PackageCatalog catalog = await JsonSerializer.DeserializeAsync<PackageCatalog>(stream, Json, token)
            ?? throw new InvalidDataException("文件清单为空。");

        ValidateCatalog(catalog, catalogUrl, installRoot);
        InstalledState state = await LoadStateAsync(installRoot, token);
        List<PackageChange> changes = new();

        foreach (PackageFile file in catalog.Files)
        {
            string destination = ResolvePath(installRoot, file.Path);
            if (!File.Exists(destination))
            {
                changes.Add(new PackageChange(file, false));
                continue;
            }

            string actualHash = await ComputeHashAsync(destination, token);
            if (actualHash.Equals(file.Sha256, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            bool modified = !state.Files.TryGetValue(file.Path, out string? priorHash)
                || !actualHash.Equals(priorHash, StringComparison.OrdinalIgnoreCase);
            changes.Add(new PackageChange(file, modified));
        }

        return new PackageCheck { Catalog = catalog, CatalogUrl = catalogUrl, Changes = changes };
    }

    public async Task InstallAsync(
        PackageCheck check,
        string installRoot,
        IProgress<(string File, long Received, long Total)> progress,
        CancellationToken token)
    {
        Directory.CreateDirectory(installRoot);
        InstalledState state = await LoadStateAsync(installRoot, token);

        foreach (PackageChange change in check.Changes)
        {
            token.ThrowIfCancellationRequested();
            if (change.IsModifiedByUser)
            {
                continue;
            }

            PackageFile file = change.File;
            string destination = ResolvePath(installRoot, file.Path);
            await EnsureUnchangedSinceCheckAsync(destination, file.Path, state, token);
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
            string partial = destination + ".part";
            if (File.Exists(partial) && (File.GetAttributes(partial) & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException($"拒绝写入符号链接：{partial}");
            }
            Uri downloadUrl = new(check.CatalogUrl, file.Url);
            await DownloadFileAsync(downloadUrl, partial, file, progress, token);

            // The old file stays intact until the new file passes size and hash checks.
            await EnsureUnchangedSinceCheckAsync(destination, file.Path, state, token);
            File.Move(partial, destination, true);
            state.Files[file.Path] = file.Sha256.ToLowerInvariant();
            state.Version = check.Catalog.Version;
            await SaveStateAsync(installRoot, state, token);
        }

        foreach (PackageFile file in check.Catalog.Files)
        {
            if (check.Changes.All(change => change.File != file))
            {
                state.Files[file.Path] = file.Sha256.ToLowerInvariant();
            }
        }

        state.Version = check.Catalog.Version;
        await SaveStateAsync(installRoot, state, token);
    }

    private async Task DownloadFileAsync(
        Uri url,
        string partial,
        PackageFile file,
        IProgress<(string File, long Received, long Total)> progress,
        CancellationToken token)
    {
        if (!IsAllowedUrl(url))
        {
            throw new InvalidDataException($"不安全的下载地址：{url}");
        }

        long existing = File.Exists(partial) ? new FileInfo(partial).Length : 0;
        if (existing == file.Size
            && string.Equals(await ComputeHashAsync(partial, token), file.Sha256, StringComparison.OrdinalIgnoreCase))
        {
            progress.Report((file.Path, existing, file.Size));
            return;
        }

        if (existing >= file.Size)
        {
            existing = 0;
        }

        using HttpRequestMessage request = new(HttpMethod.Get, url);
        if (existing > 0)
        {
            request.Headers.Range = new RangeHeaderValue(existing, null);
        }

        using HttpResponseMessage response = await client.SendAsync(
            request, HttpCompletionOption.ResponseHeadersRead, token);
        response.EnsureSuccessStatusCode();

        bool resumed = existing > 0 && response.StatusCode == HttpStatusCode.PartialContent;
        if (resumed && response.Content.Headers.ContentRange?.From != existing)
        {
            throw new InvalidDataException("服务器返回了错误的续传位置，请重试。");
        }

        if (!resumed)
        {
            existing = 0;
            if (response.StatusCode == HttpStatusCode.PartialContent)
            {
                throw new InvalidDataException("服务器返回了不完整的文件。");
            }
        }

        await using Stream source = await response.Content.ReadAsStreamAsync(token);
        await using (FileStream target = new(
            partial, resumed ? FileMode.Append : FileMode.Create, FileAccess.Write, FileShare.None, 65536, true))
        {
            byte[] buffer = new byte[65536];
            long received = existing;
            progress.Report((file.Path, received, file.Size));
            int count;
            while ((count = await source.ReadAsync(buffer, token)) > 0)
            {
                await target.WriteAsync(buffer.AsMemory(0, count), token);
                received += count;
                progress.Report((file.Path, received, file.Size));
            }
        }

        if (new FileInfo(partial).Length != file.Size
            || !string.Equals(await ComputeHashAsync(partial, token), file.Sha256, StringComparison.OrdinalIgnoreCase))
        {
            File.Delete(partial);
            throw new InvalidDataException($"{file.Path} 大小或 SHA-256 校验失败。请检查下载源。");
        }
    }

    private static void ValidateCatalog(PackageCatalog catalog, Uri catalogUrl, string installRoot)
    {
        if (string.IsNullOrWhiteSpace(catalog.Version) || catalog.Files.Count == 0)
        {
            throw new InvalidDataException("文件清单缺少版本号或文件列表。");
        }

        HashSet<string> paths = new(OperatingSystem.IsWindows()
            ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal);
        foreach (PackageFile file in catalog.Files)
        {
            ResolvePath(installRoot, file.Path);
            if (!paths.Add(file.Path.Replace('\\', '/')))
            {
                throw new InvalidDataException($"文件清单有重复路径：{file.Path}");
            }

            if (file.Size < 0 || file.Sha256.Length != 64
                || !file.Sha256.All(Uri.IsHexDigit)
                || string.IsNullOrWhiteSpace(file.Url)
                || !IsAllowedUrl(new Uri(catalogUrl, file.Url)))
            {
                throw new InvalidDataException($"文件清单条目无效：{file.Path}");
            }
        }
    }

    private static bool IsAllowedUrl(Uri uri)
    {
        return uri.Scheme == Uri.UriSchemeHttps
            || (uri.Scheme == Uri.UriSchemeHttp && uri.IsLoopback);
    }

    private static string ResolvePath(string root, string relative)
    {
        string normalized = relative.Replace('\\', '/');
        string[] segments = normalized.Split('/');
        if (string.IsNullOrWhiteSpace(relative) || Path.IsPathRooted(relative)
            || segments.Any(s => s.Length == 0 || s is "." or "..")
            || normalized.Contains(':')
            || normalized.StartsWith('.'))
        {
            throw new InvalidDataException($"文件路径不安全：{relative}");
        }

        string fullRoot = Path.GetFullPath(root);
        string path = Path.GetFullPath(Path.Combine(fullRoot, Path.Combine(segments)));
        string prefix = Path.TrimEndingDirectorySeparator(fullRoot) + Path.DirectorySeparatorChar;
        if (!path.StartsWith(prefix, OperatingSystem.IsWindows()
                ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
        {
            throw new InvalidDataException($"文件路径超出安装目录：{relative}");
        }

        string current = fullRoot;
        foreach (string segment in segments)
        {
            current = Path.Combine(current, segment);
            if ((File.Exists(current) || Directory.Exists(current))
                && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException($"拒绝访问符号链接：{relative}");
            }
        }

        return path;
    }

    private static async Task EnsureUnchangedSinceCheckAsync(
        string destination, string relative, InstalledState state, CancellationToken token)
    {
        if (!File.Exists(destination)) return;
        string actual = await ComputeHashAsync(destination, token);
        if (!state.Files.TryGetValue(relative, out string? previous)
            || !actual.Equals(previous, StringComparison.OrdinalIgnoreCase))
        {
            throw new IOException($"{relative} 在检查后已被修改，请重新检查更新；不会覆盖该文件。");
        }
    }

    private static async Task<string> ComputeHashAsync(string path, CancellationToken token)
    {
        await using FileStream stream = File.OpenRead(path);
        byte[] hash = await SHA256.HashDataAsync(stream, token);
        return Convert.ToHexStringLower(hash);
    }

    private static string StatePath(string root) => Path.Combine(root, ".thuai10-state.json");

    private static async Task<InstalledState> LoadStateAsync(string root, CancellationToken token)
    {
        if (!File.Exists(StatePath(root)))
        {
            return new InstalledState();
        }

        await using FileStream stream = File.OpenRead(StatePath(root));
        return await JsonSerializer.DeserializeAsync<InstalledState>(stream, Json, token)
            ?? new InstalledState();
    }

    private static async Task SaveStateAsync(string root, InstalledState state, CancellationToken token)
    {
        string temp = StatePath(root) + ".tmp";
        await using (FileStream stream = File.Create(temp))
        {
            await JsonSerializer.SerializeAsync(stream, state, Json, token);
        }

        File.Move(temp, StatePath(root), true);
    }

    private sealed class InstalledState
    {
        public string Version { get; set; } = string.Empty;
        public Dictionary<string, string> Files { get; set; } = new(
            OperatingSystem.IsWindows() ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal);
    }
}
