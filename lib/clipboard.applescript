use framework "AppKit"
use framework "Foundation"

-- The optional pasteboard name is for isolated integration tests. The CLI uses
-- the general pasteboard. Password text enters through stdin, never argv.
on run argv
    set operation to item 1 of argv
    set board to current application's NSPasteboard's generalPasteboard()
    if operation is "copy" and (count of argv) is 2 then
        set board to current application's NSPasteboard's pasteboardWithName:(item 2 of argv)
    else if operation is "clear" and (count of argv) is 4 then
        set board to current application's NSPasteboard's pasteboardWithName:(item 4 of argv)
    end if

    set ownershipType to "org.kp.clipboard-owner"
    if operation is "copy" then
        set inputData to current application's NSFileHandle's fileHandleWithStandardInput()'s readDataToEndOfFile()
        set secret to current application's NSString's alloc()'s initWithData:inputData encoding:(current application's NSUTF8StringEncoding)
        if secret is missing value then error "Password is not valid UTF-8"
        if (secret's |length|() as integer) is 0 then error "Password is empty"
        set token to current application's NSUUID's UUID()'s UUIDString()
        set clipboardItem to current application's NSPasteboardItem's alloc()'s init()
        -- Construct all representations before publishing the item.
        if not (clipboardItem's setString:secret forType:"public.utf8-plain-text") then error "Cannot encode password"
        clipboardItem's setString:"1" forType:"org.nspasteboard.ConcealedType"
        clipboardItem's setString:"1" forType:"org.nspasteboard.TransientType"
        clipboardItem's setString:token forType:ownershipType
        board's clearContents()
        if not (board's writeObjects:{clipboardItem}) then error "Cannot write clipboard"
        return (board's changeCount() as text) & ":" & (token as text)
    else if operation is "clear" then
        set receipt to item 2 of argv
        set parts to (current application's NSString's stringWithString:receipt)'s componentsSeparatedByString:":"
        if (parts's |count|() as integer) is not 2 then error "Invalid clipboard receipt"
        set expectedCount to (parts's objectAtIndex:0) as integer
        set expectedToken to (parts's objectAtIndex:1) as text
        current application's NSThread's sleepForTimeInterval:((item 3 of argv) as integer)
        if (board's changeCount() as integer) is expectedCount then
            set currentToken to board's stringForType:ownershipType
            if currentToken is not missing value then
                if (currentToken as text) is expectedToken then board's clearContents()
            end if
        end if
        return
    end if
    error "Unknown clipboard operation"
end run
