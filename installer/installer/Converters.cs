using Avalonia.Data.Converters;

namespace Thuai10.Launcher;

/// <summary>界面辅助转换器，只做显示判断，不涉及业务逻辑。</summary>
public static class Converters
{
    /// <summary>版本号是否为已检查到的真实版本（空值与“尚未检查”都不算）。</summary>
    public static readonly IValueConverter HasRealVersion = new FuncValueConverter<string?, bool>(
        value => !string.IsNullOrWhiteSpace(value) && value != "尚未检查");
}
